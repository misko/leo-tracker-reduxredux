#!/usr/bin/env python3
"""Three-stage, response-sealed final Doppler holdout experiment.

``predict`` writes the strict-past ledger and every satellite ranking without IQ
access. ``attach-odd`` is a separate process that verifies the prediction
receipt before reading only the authorized recording chunks. ``report`` consumes
the two immutable ledgers and never opens recording storage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from leo.analysis.research.doppler_holdout_odd_adapter import (  # noqa: E402
    AuthorizedOddChunk,
    DigestPinnedOddQinAdapter,
    GuardedOddQinFrame,
    OddChunkReadReceipt,
    OddQinFrameReadRequest,
    preflight_exact_authorized_odd_chunks,
)
from leo.analysis.research.doppler_holdout_pre_response import (  # noqa: E402
    DopplerHoldoutPredictionLedgerV1,
    build_odd_qin_target_authorities,
    build_prediction_ledger,
)
from leo.analysis.research.doppler_holdout_response_v2 import (  # noqa: E402
    OddQinAttachmentLedgerV2,
    attach_odd_qin_responses_v2,
)
from leo.analysis.research.doppler_holdout_selector_v2 import (  # noqa: E402
    DopplerHoldoutDerivedManifestV2,
)
from leo.analysis.research.final_doppler_holdout import (  # noqa: E402
    BASELINE_ASSOCIATION_METHOD,
    PRIMARY_ASSOCIATION_METHOD,
    CandidateNuisanceFit,
    FrozenAssociationBin,
    FrozenCandidateRanking,
    FrozenCaptureBinInventory,
    FrozenRollingOriginControl,
    aggregate_odd_responses_to_frozen_bins,
    fit_shared_radio_rate_sensitivity,
    freeze_association_bins,
    freeze_candidate_ranking,
    freeze_rolling_origin_controls,
    freeze_within_track_permutation_controls,
    frozen_wrong_time_offsets_s,
    quadratic_promotion_gate,
    score_forecasts,
    score_frozen_candidate_ranking,
    validate_frozen_candidate_ranking,
    validate_frozen_capture_inventory,
)
from leo.analysis.research.final_holdout_protocol import (  # noqa: E402
    CAPTURE_IDS,
    SCHEMA_V3,
    SELECTOR_FILE_SHA256,
    SELECTOR_SEMANTIC_DIGEST,
    TARGET_COUNT,
    V2_PROTOCOL_DIGEST,
    V2_PROTOCOL_PATH,
    V2_PROTOCOL_SHA256,
    load_and_validate_final_protocol,
    load_and_validate_historical_final_protocol_v2,
)
from leo.analysis.research.final_holdout_satellite import (  # noqa: E402
    StarlinkCandidatePopulation,
    visible_starlink_candidates_at_site,
)
from leo.analysis.research.legacy_tle_snapshot import (  # noqa: E402
    FrozenLegacyTleBinding,
    LegacyTleSnapshotReader,
)
from leo.contracts.digests import canonical_digest  # noqa: E402
from leo.contracts.sky import ObserverSiteV1  # noqa: E402
from leo.sky.propagation import parse_element_sets  # noqa: E402
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402


@dataclass(frozen=True, slots=True)
class _CachedSessionIq:
    start: int
    values: np.ndarray
    stream_id: str
    receiver_id: int


class _PinnedRecordingOddSource:
    """Read exact authorized chunks through RecordingStore, one session at a time."""

    def __init__(
        self,
        store: RecordingStore,
        chunks: tuple[AuthorizedOddChunk, ...],
    ) -> None:
        self._store = store
        self._chunks = chunks
        by_stream: dict[tuple[str, str], list[AuthorizedOddChunk]] = {}
        for chunk in chunks:
            by_stream.setdefault((chunk.session_id, chunk.stream_id), []).append(chunk)
        for stream_chunks in by_stream.values():
            ordered = sorted(stream_chunks, key=lambda item: item.sample_start)
            if any(
                left.sample_start + left.sample_count != right.sample_start
                for left, right in zip(ordered, ordered[1:], strict=False)
            ):
                raise ValueError("odd source requires an exactly contiguous authorized span")
        self._cache_key: tuple[str, str, int] | None = None
        self._cache: _CachedSessionIq | None = None

    def read_guarded_odd_qin_frame(
        self,
        request: OddQinFrameReadRequest,
    ) -> GuardedOddQinFrame:
        authority = request.authority
        session_id = authority.target.session_id
        session_chunks = tuple(
            item
            for item in self._chunks
            if item.session_id == session_id and item.stream_id == authority.stream_id
        )
        if not session_chunks or any(item not in session_chunks for item in request.chunks):
            raise ValueError("odd source request is outside its authorized chunk inventory")
        cache_key = (session_id, authority.stream_id, authority.receiver_id)
        if self._cache_key != cache_key:
            inspected = self._store.inspect(session_id)
            if inspected.manifest_sha256 != request.recording_manifest_sha256:
                raise ValueError("recording store manifest differs from odd authority")
            manifest_stream = next(
                (
                    item
                    for item in inspected.manifest.streams
                    if item.stream_id == authority.stream_id
                ),
                None,
            )
            if manifest_stream is None:
                raise ValueError("recording manifest lacks the authorized odd stream")
            manifest_chunks = {item.relative_path: item for item in manifest_stream.chunks}
            for expected in session_chunks:
                actual = manifest_chunks.get(expected.relative_path)
                if (
                    actual is None
                    or actual.sample_start != expected.sample_start
                    or actual.sample_count != expected.sample_count
                    or actual.compressed_sha256 != expected.compressed_sha256
                ):
                    raise ValueError("recording manifest chunk differs from odd authority")
            start = min(item.sample_start for item in session_chunks)
            stop = max(item.sample_start + item.sample_count for item in session_chunks)
            reader = self._store.reader(inspected, authority.stream_id, verify=True)
            if reader.sample_rate_hz != request.sample_rate_hz:
                raise ValueError("recording stream sample rate differs from odd authority")
            raw = reader.read(
                start,
                stop - start,
                receiver_ids=(authority.receiver_id,),
            )
            values = raw[:, 0, 0].astype(np.float32) + 1j * raw[:, 0, 1].astype(np.float32)
            self._cache = _CachedSessionIq(
                start=start,
                values=values,
                stream_id=authority.stream_id,
                receiver_id=authority.receiver_id,
            )
            self._cache_key = cache_key
        cache = self._cache
        if (
            cache is None
            or cache.stream_id != authority.stream_id
            or cache.receiver_id != authority.receiver_id
        ):
            raise ValueError("odd source cache receiver identity drifted")
        frame_content = round(302 * request.sample_rate_hz * 4.4e-6)
        start = authority.target.frame_start_sample - 1
        stop = authority.target.frame_start_sample + frame_content + 1
        local_start = start - cache.start
        local_stop = stop - cache.start
        if local_start < 0 or local_stop > cache.values.size:
            raise ValueError("guarded frame falls outside authorized cached chunks")
        return GuardedOddQinFrame(
            target=authority.target,
            samples=np.asarray(cache.values[local_start:local_stop], dtype=np.complex128),
            sample_rate_hz=request.sample_rate_hz,
            recording_manifest_sha256=request.recording_manifest_sha256,
            chunks=tuple(
                OddChunkReadReceipt(
                    relative_path=item.relative_path,
                    compressed_sha256=item.compressed_sha256,
                )
                for item in request.chunks
            ),
        )


def _load_manifest(path: Path, protocol: dict[str, Any]) -> DopplerHoldoutDerivedManifestV2:
    if "sha256:" + _sha256(path) != SELECTOR_FILE_SHA256:
        raise ValueError("selector-v2 file digest disagrees")
    manifest = DopplerHoldoutDerivedManifestV2.model_validate_json(path.read_text())
    if manifest.manifest_digest != SELECTOR_SEMANTIC_DIGEST:
        raise ValueError("selector-v2 semantic digest disagrees")
    evaluable = tuple(item for item in manifest.captures if item.status == "evaluable")
    if tuple(item.session_id for item in evaluable) != CAPTURE_IDS:
        raise ValueError("selector-v2 evaluable capture order disagrees")
    if sum(item.eligible_target_count for item in evaluable) != TARGET_COUNT:
        raise ValueError("selector-v2 denominator disagrees")
    protocol_captures = {item["session_id"]: item for item in protocol["captures"]}
    for capture in evaluable:
        binding = protocol_captures[capture.session_id]
        if (
            binding["target_mask_digest"] != capture.target_mask_digest
            or binding["target_count"] != capture.eligible_target_count
            or binding["recording_manifest_sha256"] != capture.recording_manifest_sha256
            or binding["analysis_manifest_sha256"] != capture.analysis_manifest_sha256
        ):
            raise ValueError("protocol capture authority differs from selector-v2")
    return manifest


def _load_historical_pre_response_protocol(
    active_protocol: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    """Resolve the fixed v2 authority used only to verify pre-response bytes."""

    correction = active_protocol.get("attachment_correction")
    if not isinstance(correction, dict):
        raise ValueError("active protocol has no attachment correction bridge")
    binding = correction.get("historical_v2_protocol")
    if not isinstance(binding, dict):
        raise ValueError("active protocol has no historical v2 binding")
    if (
        binding.get("path") != V2_PROTOCOL_PATH
        or binding.get("sha256") != V2_PROTOCOL_SHA256
        or binding.get("semantic_digest") != V2_PROTOCOL_DIGEST
        or binding.get("pre_response_authority_only") is not True
        or binding.get("execution_retired") is not True
    ):
        raise ValueError("historical v2 pre-response bridge authority disagrees")
    path = _REPOSITORY_ROOT / V2_PROTOCOL_PATH
    protocol = load_and_validate_historical_final_protocol_v2(
        path,
        repository_root=_REPOSITORY_ROOT,
    )
    if "sha256:" + _sha256(path) != V2_PROTOCOL_SHA256 or binding.get(
        "semantic_digest"
    ) != protocol.get("protocol_digest"):
        raise ValueError("historical v2 pre-response bridge authority disagrees")
    return path, protocol


def _validate_pre_response_bridge_paths(
    active_protocol: dict[str, Any],
    *,
    prediction_path: Path,
    bins_path: Path,
    rankings_path: Path,
    receipt_path: Path,
) -> None:
    """Require the exact response-free artifact paths frozen by v3."""

    correction = active_protocol.get("attachment_correction")
    bridge = correction.get("pre_response_bridge") if isinstance(correction, dict) else None
    if not isinstance(bridge, dict):
        raise ValueError("active protocol has no pre-response artifact bridge")
    observed = {
        "prediction_ledger_path": prediction_path,
        "association_bins_path": bins_path,
        "rankings_raw_path": rankings_path,
        "pre_response_receipt_path": receipt_path,
    }
    for key, path in observed.items():
        expected = _REPOSITORY_ROOT / str(bridge.get(key))
        if path.resolve(strict=False) != expected.resolve(strict=False):
            raise ValueError(f"pre-response bridge path disagrees: {key}")


def _load_catalogue(
    binding: dict[str, Any],
    *,
    reader: LegacyTleSnapshotReader,
    cache: dict[str, Any],
) -> Any:
    raw_sha = str(binding["raw_sha256"]).removeprefix("sha256:")
    if raw_sha not in cache:
        payload = reader.read(
            FrozenLegacyTleBinding(
                metadata_path=Path(binding["metadata_path"]),
                metadata_sha256=str(binding["metadata_sha256"]).removeprefix("sha256:"),
                raw_path=Path(binding["raw_path"]),
                raw_sha256=raw_sha,
                raw_byte_size=int(binding["raw_byte_size"]),
                satellite_count=int(binding["satellite_count"]),
                retrieved_at=str(binding["retrieved_at"]),
            )
        )
        cache[raw_sha] = parse_element_sets(payload.text)
    return cache[raw_sha]


def _freeze_population_ranking(
    inventory: FrozenCaptureBinInventory,
    population: StarlinkCandidatePopulation,
    *,
    lane: str,
) -> FrozenCandidateRanking | None:
    if len(population.norad_ids) < 2:
        return None
    return freeze_candidate_ranking(
        inventory,
        lane=lane,
        candidate_ids=tuple(str(value) for value in population.norad_ids),
        candidate_prediction_hz=population.prediction_hz,
    )


def _population_and_ranking_document(
    population: StarlinkCandidatePopulation,
    ranking: FrozenCandidateRanking | None,
    *,
    authority: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "complete" if ranking is not None else "no_result",
        "failure_reasons": [] if ranking is not None else ["insufficient_visible_candidates"],
        "population": _jsonable(asdict(population)),
        "population_authority": authority,
        "ranking": None if ranking is None else _jsonable(asdict(ranking)),
    }


def _population_authority(
    *,
    tle: dict[str, Any],
    utc_ns: np.ndarray,
    nominal_sky_frequency_hz: float,
    observer: dict[str, Any],
) -> dict[str, Any]:
    return {
        "tle_raw_sha256": tle["raw_sha256"],
        "utc_vector_digest": canonical_digest([int(value) for value in utc_ns]),
        "utc_bin_count": int(utc_ns.size),
        "observer_digest": canonical_digest(observer),
        "observer": observer,
        "nominal_sky_frequency_hz": nominal_sky_frequency_hz,
        "time_shift_s": 0.0,
        "doppler_convention": "received_minus_transmitted_equals_minus_range_rate_over_c",
    }


def _target_span_utc_ns(
    prediction: DopplerHoldoutPredictionLedgerV1,
    *,
    session_id: str,
    first_sample_utc_ns: int,
    sample_rate_hz: int,
) -> tuple[int, int]:
    values = tuple(
        first_sample_utc_ns + round(item.target.reference_sample * 1_000_000_000 / sample_rate_hz)
        for item in prediction.rows
        if item.target.session_id == session_id
    )
    if not values:
        raise ValueError("capture has no prediction targets")
    return min(values), max(values)


def _preflight_rolling_origin_controls(
    prediction: DopplerHoldoutPredictionLedgerV1,
    inventories: tuple[FrozenCaptureBinInventory, ...],
    capture_bindings: dict[str, dict[str, Any]],
) -> dict[str, tuple[FrozenRollingOriginControl, ...]]:
    """Materialize every deterministic rolling control before candidate work."""

    controls: dict[str, tuple[FrozenRollingOriginControl, ...]] = {}
    for inventory in inventories:
        if not inventory.evaluable:
            continue
        capture = capture_bindings[inventory.session_id]
        target_span = _target_span_utc_ns(
            prediction,
            session_id=inventory.session_id,
            first_sample_utc_ns=int(capture["first_sample_estimate_utc_ns"]),
            sample_rate_hz=int(capture["sample_rate_hz"]),
        )
        controls[inventory.session_id] = freeze_rolling_origin_controls(
            inventory,
            full_target_span_utc_ns=target_span,
        )
    expected = {item.session_id for item in inventories if item.evaluable}
    if set(controls) != expected:
        raise ValueError("rolling-origin preflight did not retain every evaluable capture")
    return controls


def _freeze_capture_controls(
    *,
    inventory: FrozenCaptureBinInventory,
    capture: dict[str, Any],
    protocol: dict[str, Any],
    true_population: StarlinkCandidatePopulation,
    rolling_controls: tuple[FrozenRollingOriginControl, ...],
    tle_reader: LegacyTleSnapshotReader,
    catalogue_cache: dict[str, Any],
    deadline_monotonic: float,
) -> dict[str, Any]:
    """Materialize every preregistered response-free association control."""

    times = np.asarray([item.center_utc_ns for item in inventory.bins], dtype=np.int64)
    sky_hz = float(capture["nominal_sky_frequency_hz"])
    preset_observer = {
        "latitude_deg": protocol["site"]["latitude_deg"],
        "longitude_deg": protocol["site"]["longitude_deg"],
        "altitude_m": protocol["site"]["altitude_m"],
        "label": protocol["site"]["label"],
    }
    frozen_observer = ObserverSiteV1(**preset_observer)
    output: dict[str, Any] = {}

    wrong_time: list[dict[str, Any]] = []
    catalogue = _load_catalogue(capture["tle_snapshot"], reader=tle_reader, cache=catalogue_cache)
    for offset_s in frozen_wrong_time_offsets_s():
        _require_before_deadline(deadline_monotonic)
        population = visible_starlink_candidates_at_site(
            catalogue,
            times + round(offset_s * 1_000_000_000),
            nominal_sky_frequency_hz=sky_hz,
            observer=frozen_observer,
        )
        ranking = _freeze_population_ranking(inventory, population, lane=PRIMARY_ASSOCIATION_METHOD)
        authority = _population_authority(
            tle=capture["tle_snapshot"],
            utc_ns=times + round(offset_s * 1_000_000_000),
            nominal_sky_frequency_hz=sky_hz,
            observer=preset_observer,
        )
        authority["time_shift_s"] = offset_s
        wrong_time.append(
            {
                "control_id": f"wrong-time-{offset_s:+.0f}s",
                "offset_s": offset_s,
                **_population_and_ranking_document(population, ranking, authority=authority),
            }
        )
    output["wrong_time"] = wrong_time

    permutations = []
    for permutation_control in freeze_within_track_permutation_controls(inventory):
        ranking = _freeze_population_ranking(
            permutation_control.inventory,
            true_population,
            lane=PRIMARY_ASSOCIATION_METHOD,
        )
        permutations.append(
            {
                "control_id": permutation_control.control_id,
                "permutation_index": permutation_control.permutation_index,
                "seed": permutation_control.seed,
                "inventory": _jsonable(asdict(permutation_control.inventory)),
                "population_authority": "inherits_true_time_population",
                "status": "complete" if ranking is not None else "no_result",
                "ranking": None if ranking is None else _jsonable(asdict(ranking)),
            }
        )
    output["within_track_permutations"] = permutations

    rolling = []
    for rolling_control in rolling_controls:
        ranking = (
            _freeze_population_ranking(
                rolling_control.inventory,
                true_population,
                lane=PRIMARY_ASSOCIATION_METHOD,
            )
            if rolling_control.inventory.evaluable
            else None
        )
        rolling.append(
            {
                "control_id": rolling_control.control_id,
                "training_fraction": rolling_control.training_fraction,
                "split_cutoff_utc_ns": rolling_control.split_cutoff_utc_ns,
                "target_span_start_utc_ns": rolling_control.target_span_start_utc_ns,
                "target_span_stop_utc_ns": rolling_control.target_span_stop_utc_ns,
                "inventory": _jsonable(asdict(rolling_control.inventory)),
                "population_authority": "inherits_true_time_population",
                "status": "complete" if ranking is not None else "no_result",
                "ranking": None if ranking is None else _jsonable(asdict(ranking)),
            }
        )
    output["rolling_origins"] = rolling

    utc_sensitivity = []
    estimate = int(capture["first_sample_estimate_utc_ns"])
    for utc_authority_label in ("earliest", "latest"):
        _require_before_deadline(deadline_monotonic)
        origin = int(capture[f"first_sample_{utc_authority_label}_utc_ns"])
        population = visible_starlink_candidates_at_site(
            catalogue,
            times + (origin - estimate),
            nominal_sky_frequency_hz=sky_hz,
            observer=frozen_observer,
        )
        ranking = _freeze_population_ranking(inventory, population, lane=PRIMARY_ASSOCIATION_METHOD)
        utc_sensitivity.append(
            {
                "control_id": f"utc-{utc_authority_label}",
                "first_sample_utc_ns": origin,
                **_population_and_ranking_document(
                    population,
                    ranking,
                    authority=_population_authority(
                        tle=capture["tle_snapshot"],
                        utc_ns=times + (origin - estimate),
                        nominal_sky_frequency_hz=sky_hz,
                        observer=preset_observer,
                    ),
                ),
            }
        )
    output["utc_bounds"] = utc_sensitivity

    site_sensitivity = []
    for site in protocol["association"]["site_sensitivity"]:
        _require_before_deadline(deadline_monotonic)
        observer = ObserverSiteV1(
            latitude_deg=float(site["latitude_deg"]),
            longitude_deg=float(site["longitude_deg"]),
            altitude_m=float(site["altitude_m"]),
            label=str(site["label"]),
        )
        population = visible_starlink_candidates_at_site(
            catalogue,
            times,
            nominal_sky_frequency_hz=sky_hz,
            observer=observer,
        )
        ranking = _freeze_population_ranking(inventory, population, lane=PRIMARY_ASSOCIATION_METHOD)
        site_sensitivity.append(
            {
                "control_id": str(site["control_id"]),
                "observer": observer.model_dump(mode="json"),
                **_population_and_ranking_document(
                    population,
                    ranking,
                    authority=_population_authority(
                        tle=capture["tle_snapshot"],
                        utc_ns=times,
                        nominal_sky_frequency_hz=sky_hz,
                        observer={
                            "latitude_deg": observer.latitude_deg,
                            "longitude_deg": observer.longitude_deg,
                            "altitude_m": observer.altitude_m,
                            "label": observer.label,
                        },
                    ),
                ),
            }
        )
    output["site_sensitivity"] = site_sensitivity

    _require_before_deadline(deadline_monotonic)
    predecessor_catalogue = _load_catalogue(
        capture["predecessor_tle_snapshot"],
        reader=tle_reader,
        cache=catalogue_cache,
    )
    predecessor_population = visible_starlink_candidates_at_site(
        predecessor_catalogue,
        times,
        nominal_sky_frequency_hz=sky_hz,
        observer=frozen_observer,
    )
    predecessor_ranking = _freeze_population_ranking(
        inventory,
        predecessor_population,
        lane=PRIMARY_ASSOCIATION_METHOD,
    )
    output["predecessor_tle"] = {
        "control_id": "predecessor-tle",
        "raw_sha256": capture["predecessor_tle_snapshot"]["raw_sha256"],
        **_population_and_ranking_document(
            predecessor_population,
            predecessor_ranking,
            authority=_population_authority(
                tle=capture["predecessor_tle_snapshot"],
                utc_ns=times,
                nominal_sky_frequency_hz=sky_hz,
                observer=preset_observer,
            ),
        ),
    }
    return output


def _predict(arguments: argparse.Namespace) -> None:
    started_monotonic = time.monotonic()
    started_time_ns = time.time_ns()
    protocol_path = Path(arguments.protocol)
    protocol = load_and_validate_final_protocol(
        protocol_path,
        repository_root=_REPOSITORY_ROOT,
    )
    if protocol.get("schema") == SCHEMA_V3:
        raise ValueError("protocol v3 is attachment/report-only; pre-response rerun forbidden")
    deadline_monotonic = started_monotonic + float(
        protocol["association"]["maximum_pre_response_compute_seconds"]
    )
    manifest_path = Path(protocol["selector_v2"]["path"])
    if not manifest_path.is_absolute():
        manifest_path = _REPOSITORY_ROOT / manifest_path
    manifest = _load_manifest(manifest_path, protocol)
    predictor_path = _REPOSITORY_ROOT / "src/leo/analysis/research/doppler_holdout_pre_response.py"
    prediction = build_prediction_ledger(
        manifest,
        source_v2_file_sha256=SELECTOR_FILE_SHA256,
        forecast_implementation_sha256="sha256:" + _sha256(predictor_path),
    )
    if prediction.target_count != TARGET_COUNT:
        raise ValueError("prediction ledger did not retain all 5,413 targets")
    capture_bindings = {item["session_id"]: item for item in protocol["captures"]}
    inventories = freeze_association_bins(
        prediction,
        first_sample_utc_ns={
            session: int(item["first_sample_estimate_utc_ns"])
            for session, item in capture_bindings.items()
        },
        sample_rate_hz={
            session: int(item["sample_rate_hz"]) for session, item in capture_bindings.items()
        },
    )
    output = Path(arguments.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    arguments._output_dir_created_by_run = True
    prediction_path = output / "prediction-ledger.json"
    bins_path = output / "association-bin-inventory.json"
    ranking_path = output / "pre-response-rankings.json"
    prediction_path.write_text(prediction.model_dump_json(indent=2) + "\n")
    bins_document = {
        "schema": "org.leo.research.final-holdout-association-bins/v1",
        "prediction_ledger_digest": prediction.ledger_digest,
        "response_accessed": False,
        "inventories": [_jsonable(asdict(item)) for item in inventories],
    }
    bins_document["bins_digest"] = canonical_digest(bins_document)
    _write_json(bins_path, bins_document)
    _validate_pre_response_replay_artifacts(
        protocol,
        prediction=prediction,
        prediction_path=prediction_path,
        bins_document=bins_document,
        bins_path=bins_path,
    )
    try:
        rolling_controls_by_session = _preflight_rolling_origin_controls(
            prediction,
            inventories,
            capture_bindings,
        )
    except BaseException as error:
        try:
            _write_predict_failure_status(
                arguments,
                started_time_ns=started_time_ns,
                error=error,
                traceback_text=traceback.format_exc(),
            )
        except Exception as status_error:
            print(
                f"unable to persist pre-response failure status: {status_error}",
                file=sys.stderr,
            )
        raise
    arguments._candidate_work_started = True
    tle_reader = LegacyTleSnapshotReader()
    catalogue_cache: dict[str, Any] = {}
    rankings: list[dict[str, Any]] = []
    primary_rankings: list[FrozenCandidateRanking] = []
    primary_inventories: list[FrozenCaptureBinInventory] = []
    for inventory in inventories:
        _require_before_deadline(deadline_monotonic)
        capture = capture_bindings[inventory.session_id]
        if not inventory.evaluable:
            rankings.append(
                {
                    "session_id": inventory.session_id,
                    "evaluable": False,
                    "failure_reasons": list(inventory.failure_reasons),
                    "population": None,
                    "primary": None,
                    "baseline": None,
                    "controls": {"status": "inventory_not_evaluable"},
                }
            )
            continue
        catalogue = _load_catalogue(
            capture["tle_snapshot"], reader=tle_reader, cache=catalogue_cache
        )
        frozen_observer = ObserverSiteV1(
            latitude_deg=float(protocol["site"]["latitude_deg"]),
            longitude_deg=float(protocol["site"]["longitude_deg"]),
            altitude_m=float(protocol["site"]["altitude_m"]),
            label=str(protocol["site"]["label"]),
        )
        population = visible_starlink_candidates_at_site(
            catalogue,
            np.asarray([item.center_utc_ns for item in inventory.bins], dtype=np.int64),
            nominal_sky_frequency_hz=float(capture["nominal_sky_frequency_hz"]),
            observer=frozen_observer,
        )
        true_population_authority = _population_authority(
            tle=capture["tle_snapshot"],
            utc_ns=np.asarray([item.center_utc_ns for item in inventory.bins], dtype=np.int64),
            nominal_sky_frequency_hz=float(capture["nominal_sky_frequency_hz"]),
            observer={
                "latitude_deg": protocol["site"]["latitude_deg"],
                "longitude_deg": protocol["site"]["longitude_deg"],
                "altitude_m": protocol["site"]["altitude_m"],
                "label": protocol["site"]["label"],
            },
        )
        primary = _freeze_population_ranking(inventory, population, lane=PRIMARY_ASSOCIATION_METHOD)
        baseline = _freeze_population_ranking(
            inventory, population, lane=BASELINE_ASSOCIATION_METHOD
        )
        if primary is None or baseline is None:
            rankings.append(
                {
                    "session_id": inventory.session_id,
                    "evaluable": False,
                    "failure_reasons": ["insufficient_visible_candidates"],
                    "population": _jsonable(asdict(population)),
                    "population_authority": true_population_authority,
                    "primary": None,
                    "baseline": None,
                    "controls": {"status": "candidate_population_not_evaluable"},
                }
            )
            continue
        primary_rankings.append(primary)
        primary_inventories.append(inventory)
        rankings.append(
            {
                "session_id": inventory.session_id,
                "evaluable": True,
                "failure_reasons": [],
                "population": _jsonable(asdict(population)),
                "population_authority": true_population_authority,
                "primary": _jsonable(asdict(primary)),
                "baseline": _jsonable(asdict(baseline)),
                "controls": _freeze_capture_controls(
                    inventory=inventory,
                    capture=capture,
                    protocol=protocol,
                    true_population=population,
                    rolling_controls=rolling_controls_by_session[inventory.session_id],
                    tle_reader=tle_reader,
                    catalogue_cache=catalogue_cache,
                    deadline_monotonic=deadline_monotonic,
                ),
            }
        )
    if primary_rankings:
        shared_rate = fit_shared_radio_rate_sensitivity(
            primary_rankings,
            primary_inventories,
            physical_radio_by_session={
                item.session_id: str(capture_bindings[item.session_id]["shared_rate_group_id"])
                for item in primary_rankings
            },
        )
        shared_rate_document: dict[str, Any] = {
            "status": "complete",
            "sensitivity": _jsonable(asdict(shared_rate)),
        }
    else:
        shared_rate_document = {
            "status": "no_result",
            "failure_reasons": ["no_evaluable_true_time_rankings"],
        }
    _require_before_deadline(deadline_monotonic)
    ranking_document = {
        "schema": "org.leo.research.final-holdout-pre-response-rankings/v1",
        "prediction_ledger_digest": prediction.ledger_digest,
        "response_accessed": False,
        "control_configuration": {
            "wrong_time_offsets_s": protocol["association"]["wrong_time_offsets_s"],
            "within_track_permutation_count": protocol["association"]["within_track_permutations"],
            "within_track_permutation_seed": protocol["association"][
                "within_track_permutation_seed"
            ],
            "rolling_origin_training_fractions": protocol["association"][
                "rolling_origin_training_fractions"
            ],
        },
        "shared_physical_radio_rate_sensitivity": shared_rate_document,
        "rankings": rankings,
    }
    ranking_document["ranking_digest"] = canonical_digest(ranking_document)
    _write_json(ranking_path, ranking_document)
    receipt = {
        "schema": "org.leo.research.final-holdout-pre-response-receipt/v1",
        "protocol_sha256": "sha256:" + _sha256(protocol_path),
        "protocol_digest": protocol["protocol_digest"],
        "prediction_ledger_digest": prediction.ledger_digest,
        "target_count": prediction.target_count,
        "satellites_propagated_or_ranked_before_protocol_freeze": False,
        "odd_iq_accessed": False,
        "odd_responses_accessed": False,
        "runtime_seconds": time.monotonic() - started_monotonic,
        "maximum_pre_response_compute_seconds": protocol["association"][
            "maximum_pre_response_compute_seconds"
        ],
        "artifacts": {
            "prediction_ledger": {
                "basename": prediction_path.name,
                "sha256": "sha256:" + _sha256(prediction_path),
                "semantic_digest": prediction.ledger_digest,
            },
            "association_bins": {
                "basename": bins_path.name,
                "sha256": "sha256:" + _sha256(bins_path),
                "semantic_digest": bins_document["bins_digest"],
            },
            "rankings_and_controls": {
                "basename": ranking_path.name,
                "sha256": "sha256:" + _sha256(ranking_path),
                "semantic_digest": ranking_document["ranking_digest"],
            },
        },
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    _write_json(output / "pre-response-receipt.json", receipt)


def _inventory_from_document(value: object) -> FrozenCaptureBinInventory:
    if not isinstance(value, dict):
        raise ValueError("frozen inventory must be an object")
    raw_bins = value.get("bins")
    if not isinstance(raw_bins, list):
        raise ValueError("frozen inventory bins must be an array")
    bins = tuple(
        FrozenAssociationBin(
            session_id=str(item["session_id"]),
            bin_id=int(item["bin_id"]),
            center_utc_ns=int(item["center_utc_ns"]),
            target_count=int(item["target_count"]),
            target_frame_start_samples=tuple(
                int(target) for target in item["target_frame_start_samples"]
            ),
            primary_cfo_hz=float(item["primary_cfo_hz"]),
            baseline_cfo_hz=float(item["baseline_cfo_hz"]),
            split=str(item["split"]),
        )
        for item in raw_bins
    )
    inventory = FrozenCaptureBinInventory(
        session_id=str(value["session_id"]),
        prediction_ledger_digest=str(value["prediction_ledger_digest"]),
        bins=bins,
        evaluable=value.get("evaluable") is True,
        failure_reasons=tuple(str(item) for item in value["failure_reasons"]),
    )
    validate_frozen_capture_inventory(inventory)
    return inventory


def _ranking_from_document(
    value: object,
    inventory: FrozenCaptureBinInventory,
) -> FrozenCandidateRanking:
    if not isinstance(value, dict):
        raise ValueError("frozen ranking must be an object")
    raw_fits = value.get("fits")
    if not isinstance(raw_fits, list):
        raise ValueError("frozen ranking fits must be an array")
    ranking = FrozenCandidateRanking(
        session_id=str(value["session_id"]),
        lane=str(value["lane"]),
        candidate_ids=tuple(str(item) for item in value["candidate_ids"]),
        candidate_prediction_hz=tuple(
            tuple(float(item) for item in row) for row in value["candidate_prediction_hz"]
        ),
        fits=tuple(
            CandidateNuisanceFit(
                candidate_id=str(item["candidate_id"]),
                training_rms_hz=float(item["training_rms_hz"]),
                offset_hz=float(item["offset_hz"]),
                rate_departure_hz_s=float(item["rate_departure_hz_s"]),
                rank=int(item["rank"]),
            )
            for item in raw_fits
        ),
        training_bin_ids=tuple(int(item) for item in value["training_bin_ids"]),
        evaluation_bin_ids=tuple(int(item) for item in value["evaluation_bin_ids"]),
        response_accessed=value.get("response_accessed") is True,
    )
    validate_frozen_candidate_ranking(ranking, inventory)
    recomputed = freeze_candidate_ranking(
        inventory,
        lane=ranking.lane,
        candidate_ids=ranking.candidate_ids,
        candidate_prediction_hz=np.asarray(ranking.candidate_prediction_hz, dtype=float),
    )
    if ranking != recomputed:
        raise ValueError("frozen ranking differs from the offset-only optimum")
    return ranking


def _validate_population_binding(
    value: object,
    *,
    inventory: FrozenCaptureBinInventory,
    ranking: FrozenCandidateRanking | None,
) -> None:
    if not isinstance(value, dict):
        raise ValueError("candidate population must be an object")
    required = {
        "catalogue_indices",
        "norad_ids",
        "names",
        "prediction_hz",
        "minimum_elevation_deg",
        "maximum_elevation_deg",
        "coarse_candidate_count",
    }
    if set(value) != required:
        raise ValueError("candidate population fields drifted")
    identifiers = tuple(str(item) for item in value["norad_ids"])
    predictions = value["prediction_hz"]
    count = len(identifiers)
    if (
        len(set(identifiers)) != count
        or len(value["catalogue_indices"]) != count
        or len(value["names"]) != count
        or len(predictions) != count
        or len(value["minimum_elevation_deg"]) != count
        or len(value["maximum_elevation_deg"]) != count
        or any(len(row) != len(inventory.bins) for row in predictions)
        or int(value["coarse_candidate_count"]) < count
    ):
        raise ValueError("candidate population shape disagrees")
    if ranking is not None and (
        ranking.candidate_ids != identifiers
        or ranking.candidate_prediction_hz
        != tuple(tuple(float(item) for item in row) for row in predictions)
    ):
        raise ValueError("candidate population differs from frozen ranking")


def _validate_population_authority(
    value: object,
    *,
    inventory: FrozenCaptureBinInventory,
) -> None:
    if not isinstance(value, dict) or set(value) != {
        "tle_raw_sha256",
        "utc_vector_digest",
        "utc_bin_count",
        "observer_digest",
        "observer",
        "nominal_sky_frequency_hz",
        "time_shift_s",
        "doppler_convention",
    }:
        raise ValueError("candidate population authority is incomplete")
    if (
        value["utc_bin_count"] != len(inventory.bins)
        or value["observer_digest"] != canonical_digest(value["observer"])
        or not math.isfinite(float(value["nominal_sky_frequency_hz"]))
        or float(value["nominal_sky_frequency_hz"]) <= 0.0
        or value["doppler_convention"]
        != "received_minus_transmitted_equals_minus_range_rate_over_c"
    ):
        raise ValueError("candidate population authority drifted")


def _validate_control_entry(
    entry: object,
    *,
    inventory: FrozenCaptureBinInventory,
) -> FrozenCandidateRanking | None:
    if not isinstance(entry, dict):
        raise ValueError("association control entry must be an object")
    ranking_value = entry.get("ranking")
    ranking = None if ranking_value is None else _ranking_from_document(ranking_value, inventory)
    if (entry.get("status") == "complete") != (ranking is not None):
        raise ValueError("association control status disagrees with its ranking")
    population = entry.get("population")
    if population is not None:
        _validate_population_binding(population, inventory=inventory, ranking=ranking)
        _validate_population_authority(entry.get("population_authority"), inventory=inventory)
        population_count = len(population["norad_ids"])
        if ranking is not None and population_count < 2:
            raise ValueError("complete association control lacks candidate support")
        if ranking is None and (
            population_count >= 2
            or entry.get("failure_reasons") != ["insufficient_visible_candidates"]
        ):
            raise ValueError("association control no-result accounting drifted")
    return ranking


def _validate_frozen_rankings_and_controls(
    document: dict[str, Any],
    *,
    prediction: DopplerHoldoutPredictionLedgerV1,
    inventories: tuple[FrozenCaptureBinInventory, ...],
    protocol: dict[str, Any],
) -> None:
    if document.get("control_configuration") != {
        "wrong_time_offsets_s": protocol["association"]["wrong_time_offsets_s"],
        "within_track_permutation_count": protocol["association"]["within_track_permutations"],
        "within_track_permutation_seed": protocol["association"]["within_track_permutation_seed"],
        "rolling_origin_training_fractions": protocol["association"][
            "rolling_origin_training_fractions"
        ],
    }:
        raise ValueError("ranking/control configuration drifted")
    raw_rows = document["rankings"]
    inventory_by_session = {item.session_id: item for item in inventories}
    capture_by_session = {item["session_id"]: item for item in protocol["captures"]}
    primary_rankings: list[FrozenCandidateRanking] = []
    primary_inventories: list[FrozenCaptureBinInventory] = []
    for row in raw_rows:
        session_id = str(row["session_id"])
        inventory = inventory_by_session[session_id]
        if row.get("evaluable") is not True:
            if row.get("primary") is not None or row.get("baseline") is not None:
                raise ValueError("non-evaluable capture retains a ranking")
            if not inventory.evaluable:
                if (
                    tuple(row.get("failure_reasons", ())) != inventory.failure_reasons
                    or row.get("population") is not None
                    or row.get("controls") != {"status": "inventory_not_evaluable"}
                ):
                    raise ValueError("non-evaluable inventory accounting drifted")
            else:
                population = row.get("population")
                _validate_population_binding(population, inventory=inventory, ranking=None)
                if (
                    tuple(row.get("failure_reasons", ())) != ("insufficient_visible_candidates",)
                    or not isinstance(population, dict)
                    or len(population["norad_ids"]) >= 2
                    or row.get("controls") != {"status": "candidate_population_not_evaluable"}
                ):
                    raise ValueError("candidate-population failure accounting drifted")
            continue
        if not inventory.evaluable:
            raise ValueError("non-evaluable inventory cannot have rankings")
        primary = _ranking_from_document(row.get("primary"), inventory)
        baseline = _ranking_from_document(row.get("baseline"), inventory)
        if primary.lane != PRIMARY_ASSOCIATION_METHOD or baseline.lane != (
            BASELINE_ASSOCIATION_METHOD
        ):
            raise ValueError("true-time association lanes drifted")
        if (
            primary.candidate_ids != baseline.candidate_ids
            or primary.candidate_prediction_hz != baseline.candidate_prediction_hz
        ):
            raise ValueError("primary and baseline candidate populations differ")
        _validate_population_binding(row.get("population"), inventory=inventory, ranking=primary)
        true_times = np.asarray([item.center_utc_ns for item in inventory.bins], dtype=np.int64)
        true_authority = _population_authority(
            tle=capture_by_session[session_id]["tle_snapshot"],
            utc_ns=true_times,
            nominal_sky_frequency_hz=float(
                capture_by_session[session_id]["nominal_sky_frequency_hz"]
            ),
            observer={
                "latitude_deg": protocol["site"]["latitude_deg"],
                "longitude_deg": protocol["site"]["longitude_deg"],
                "altitude_m": protocol["site"]["altitude_m"],
                "label": protocol["site"]["label"],
            },
        )
        if row.get("population_authority") != true_authority:
            raise ValueError("true-time candidate population authority drifted")
        primary_rankings.append(primary)
        primary_inventories.append(inventory)

        controls = row.get("controls")
        if not isinstance(controls, dict):
            raise ValueError("capture controls are absent")
        wrong_time = controls.get("wrong_time")
        if (
            not isinstance(wrong_time, list)
            or tuple(float(item.get("offset_s", math.nan)) for item in wrong_time)
            != frozen_wrong_time_offsets_s()
        ):
            raise ValueError("wrong-time control family drifted")
        for entry, offset_s in zip(wrong_time, frozen_wrong_time_offsets_s(), strict=True):
            if entry.get("control_id") != f"wrong-time-{offset_s:+.0f}s":
                raise ValueError("wrong-time control identity drifted")
            expected_authority = _population_authority(
                tle=capture_by_session[session_id]["tle_snapshot"],
                utc_ns=true_times + round(offset_s * 1_000_000_000),
                nominal_sky_frequency_hz=float(
                    capture_by_session[session_id]["nominal_sky_frequency_hz"]
                ),
                observer=true_authority["observer"],
            )
            expected_authority["time_shift_s"] = offset_s
            if entry.get("population_authority") != expected_authority:
                raise ValueError("wrong-time population authority drifted")
            _validate_control_entry(entry, inventory=inventory)

        expected_permutations = freeze_within_track_permutation_controls(inventory)
        permutations = controls.get("within_track_permutations")
        if not isinstance(permutations, list) or len(permutations) != len(expected_permutations):
            raise ValueError("permutation control family drifted")
        for entry, expected_permutation in zip(permutations, expected_permutations, strict=True):
            control_inventory = _inventory_from_document(entry.get("inventory"))
            if control_inventory != expected_permutation.inventory or (
                entry.get("control_id"),
                entry.get("permutation_index"),
                entry.get("seed"),
            ) != (
                expected_permutation.control_id,
                expected_permutation.permutation_index,
                expected_permutation.seed,
            ):
                raise ValueError("permutation control authority drifted")
            if entry.get("population_authority") != "inherits_true_time_population":
                raise ValueError("permutation population authority drifted")
            if _validate_control_entry(entry, inventory=control_inventory) is None:
                raise ValueError("evaluable permutation control lacks a ranking")

        capture = capture_by_session[session_id]
        target_span = _target_span_utc_ns(
            prediction,
            session_id=session_id,
            first_sample_utc_ns=int(capture["first_sample_estimate_utc_ns"]),
            sample_rate_hz=int(capture["sample_rate_hz"]),
        )
        expected_origins = freeze_rolling_origin_controls(
            inventory, full_target_span_utc_ns=target_span
        )
        origins = controls.get("rolling_origins")
        if not isinstance(origins, list) or len(origins) != len(expected_origins):
            raise ValueError("rolling-origin control family drifted")
        for entry, expected_origin in zip(origins, expected_origins, strict=True):
            control_inventory = _inventory_from_document(entry.get("inventory"))
            if control_inventory != expected_origin.inventory or entry.get("control_id") != (
                expected_origin.control_id
            ):
                raise ValueError("rolling-origin control authority drifted")
            if entry.get("population_authority") != "inherits_true_time_population":
                raise ValueError("rolling-origin population authority drifted")
            ranking = _validate_control_entry(entry, inventory=control_inventory)
            if control_inventory.evaluable != (ranking is not None):
                raise ValueError("rolling-origin ranking support drifted")

        utc_bounds = controls.get("utc_bounds")
        expected_utc = (
            ("utc-earliest", int(capture["first_sample_earliest_utc_ns"])),
            ("utc-latest", int(capture["first_sample_latest_utc_ns"])),
        )
        if (
            not isinstance(utc_bounds, list)
            or tuple(
                (item.get("control_id"), item.get("first_sample_utc_ns")) for item in utc_bounds
            )
            != expected_utc
        ):
            raise ValueError("UTC sensitivity authority drifted")
        for entry in utc_bounds:
            origin = int(entry["first_sample_utc_ns"])
            estimate = int(capture["first_sample_estimate_utc_ns"])
            expected_authority = _population_authority(
                tle=capture["tle_snapshot"],
                utc_ns=true_times + (origin - estimate),
                nominal_sky_frequency_hz=float(capture["nominal_sky_frequency_hz"]),
                observer=true_authority["observer"],
            )
            if entry.get("population_authority") != expected_authority:
                raise ValueError("UTC population authority drifted")
            _validate_control_entry(entry, inventory=inventory)

        sites = controls.get("site_sensitivity")
        expected_sites = protocol["association"]["site_sensitivity"]
        if not isinstance(sites, list) or tuple(item.get("control_id") for item in sites) != (
            tuple(item["control_id"] for item in expected_sites)
        ):
            raise ValueError("site sensitivity authority drifted")
        for entry, expected_site in zip(sites, expected_sites, strict=True):
            if entry.get("observer") != {
                "schema_version": 1,
                "latitude_deg": expected_site["latitude_deg"],
                "longitude_deg": expected_site["longitude_deg"],
                "altitude_m": expected_site["altitude_m"],
                "label": expected_site["label"],
            }:
                raise ValueError("site sensitivity coordinates drifted")
            expected_authority = _population_authority(
                tle=capture["tle_snapshot"],
                utc_ns=true_times,
                nominal_sky_frequency_hz=float(capture["nominal_sky_frequency_hz"]),
                observer={
                    "latitude_deg": expected_site["latitude_deg"],
                    "longitude_deg": expected_site["longitude_deg"],
                    "altitude_m": expected_site["altitude_m"],
                    "label": expected_site["label"],
                },
            )
            if entry.get("population_authority") != expected_authority:
                raise ValueError("site population authority drifted")
            _validate_control_entry(entry, inventory=inventory)

        predecessor = controls.get("predecessor_tle")
        if (
            not isinstance(predecessor, dict)
            or predecessor.get("control_id") != "predecessor-tle"
            or predecessor.get("raw_sha256") != capture["predecessor_tle_snapshot"]["raw_sha256"]
        ):
            raise ValueError("predecessor-TLE control authority drifted")
        expected_predecessor_authority = _population_authority(
            tle=capture["predecessor_tle_snapshot"],
            utc_ns=true_times,
            nominal_sky_frequency_hz=float(capture["nominal_sky_frequency_hz"]),
            observer=true_authority["observer"],
        )
        if predecessor.get("population_authority") != expected_predecessor_authority:
            raise ValueError("predecessor-TLE population authority drifted")
        _validate_control_entry(predecessor, inventory=inventory)

    shared = document.get("shared_physical_radio_rate_sensitivity")
    if primary_rankings:
        if not isinstance(shared, dict) or shared.get("status") != "complete":
            raise ValueError("shared-radio sensitivity is absent")
        recomputed = fit_shared_radio_rate_sensitivity(
            primary_rankings,
            primary_inventories,
            physical_radio_by_session={
                item.session_id: str(capture_by_session[item.session_id]["shared_rate_group_id"])
                for item in primary_rankings
            },
        )
        if shared.get("sensitivity") != _jsonable(asdict(recomputed)):
            raise ValueError("shared-radio sensitivity differs from frozen rankings")
    elif shared != {
        "status": "no_result",
        "failure_reasons": ["no_evaluable_true_time_rankings"],
    }:
        raise ValueError("shared-radio no-result accounting drifted")


def _load_pre_response_authority(
    *,
    protocol_path: Path,
    protocol: dict[str, Any],
    prediction_path: Path,
    bins_path: Path,
    rankings_path: Path,
    receipt_path: Path,
) -> DopplerHoldoutPredictionLedgerV1:
    """Verify every durable pre-response artifact before storage can be opened."""

    receipt = _load_json_file(receipt_path)
    expected_receipt_keys = {
        "schema",
        "protocol_sha256",
        "protocol_digest",
        "prediction_ledger_digest",
        "target_count",
        "satellites_propagated_or_ranked_before_protocol_freeze",
        "odd_iq_accessed",
        "odd_responses_accessed",
        "runtime_seconds",
        "maximum_pre_response_compute_seconds",
        "artifacts",
        "receipt_digest",
    }
    if not isinstance(receipt, dict) or receipt.get("schema") != (
        "org.leo.research.final-holdout-pre-response-receipt/v1"
    ):
        raise ValueError("pre-response receipt schema is invalid")
    if set(receipt) != expected_receipt_keys:
        raise ValueError("pre-response receipt key set is invalid")
    receipt_digest = receipt.get("receipt_digest")
    if receipt_digest != canonical_digest(
        {key: value for key, value in receipt.items() if key != "receipt_digest"}
    ):
        raise ValueError("pre-response receipt digest disagrees")
    if (
        receipt.get("protocol_sha256") != "sha256:" + _sha256(protocol_path)
        or receipt.get("protocol_digest") != protocol["protocol_digest"]
        or receipt.get("prediction_ledger_digest") is None
        or receipt.get("target_count") != TARGET_COUNT
        or receipt.get("satellites_propagated_or_ranked_before_protocol_freeze") is not False
        or receipt.get("odd_iq_accessed") is not False
        or receipt.get("odd_responses_accessed") is not False
        or not isinstance(receipt.get("runtime_seconds"), (int, float))
        or not 0.0
        <= float(receipt["runtime_seconds"])
        <= float(protocol["association"]["maximum_pre_response_compute_seconds"])
        or receipt.get("maximum_pre_response_compute_seconds")
        != protocol["association"]["maximum_pre_response_compute_seconds"]
    ):
        raise ValueError("pre-response receipt chronology or protocol authority disagrees")
    artifacts = receipt.get("artifacts")
    expected_paths = {
        "prediction_ledger": prediction_path,
        "association_bins": bins_path,
        "rankings_and_controls": rankings_path,
    }
    if not isinstance(artifacts, dict) or set(artifacts) != set(expected_paths):
        raise ValueError("pre-response receipt artifact inventory is not exact")
    for key, path in expected_paths.items():
        binding = artifacts.get(key)
        if (
            not isinstance(binding, dict)
            or set(binding) != {"basename", "sha256", "semantic_digest"}
            or binding.get("basename") != path.name
            or binding.get("sha256") != "sha256:" + _sha256(path)
        ):
            raise ValueError(f"pre-response artifact binding disagrees: {key}")

    prediction = DopplerHoldoutPredictionLedgerV1.model_validate(_load_json_file(prediction_path))
    selector_path = Path(protocol["selector_v2"]["path"])
    if not selector_path.is_absolute():
        selector_path = _REPOSITORY_ROOT / selector_path
    selector_manifest = _load_manifest(selector_path, protocol)
    predictor_path = _REPOSITORY_ROOT / "src/leo/analysis/research/doppler_holdout_pre_response.py"
    expected_prediction = build_prediction_ledger(
        selector_manifest,
        source_v2_file_sha256=SELECTOR_FILE_SHA256,
        forecast_implementation_sha256="sha256:" + _sha256(predictor_path),
    )
    if (
        prediction.target_count != TARGET_COUNT
        or receipt.get("prediction_ledger_digest") != prediction.ledger_digest
        or artifacts["prediction_ledger"]["semantic_digest"] != prediction.ledger_digest
        or prediction.future_odd_qin_outcomes_opened
        or prediction.target_even_numeric_cfo_consumed
    ):
        raise ValueError("pre-response prediction ledger authority disagrees")
    if prediction != expected_prediction:
        raise ValueError("prediction ledger differs from exact selector recomputation")

    bins = _load_json_file(bins_path)
    if not isinstance(bins, dict) or bins.get("schema") != (
        "org.leo.research.final-holdout-association-bins/v1"
    ):
        raise ValueError("association-bin artifact schema is invalid")
    if bins.get("bins_digest") != canonical_digest(
        {key: value for key, value in bins.items() if key != "bins_digest"}
    ):
        raise ValueError("association-bin artifact digest disagrees")
    inventories = bins.get("inventories")
    if (
        bins.get("prediction_ledger_digest") != prediction.ledger_digest
        or bins.get("response_accessed") is not False
        or not isinstance(inventories, list)
        or tuple(item.get("session_id") for item in inventories) != CAPTURE_IDS
        or artifacts["association_bins"]["semantic_digest"] != bins["bins_digest"]
    ):
        raise ValueError("association-bin artifact authority disagrees")
    frozen_inventories = tuple(_inventory_from_document(item) for item in inventories)
    if tuple(item.prediction_ledger_digest for item in frozen_inventories) != (
        (prediction.ledger_digest,) * len(frozen_inventories)
    ):
        raise ValueError("association bins use another prediction ledger")
    capture_bindings = {item["session_id"]: item for item in protocol["captures"]}
    expected_inventories = freeze_association_bins(
        prediction,
        first_sample_utc_ns={
            session: int(item["first_sample_estimate_utc_ns"])
            for session, item in capture_bindings.items()
        },
        sample_rate_hz={
            session: int(item["sample_rate_hz"]) for session, item in capture_bindings.items()
        },
    )
    if frozen_inventories != expected_inventories:
        raise ValueError("association bins differ from the frozen prediction ledger")

    rankings = _load_json_file(rankings_path)
    if not isinstance(rankings, dict) or rankings.get("schema") != (
        "org.leo.research.final-holdout-pre-response-rankings/v1"
    ):
        raise ValueError("ranking/control artifact schema is invalid")
    if rankings.get("ranking_digest") != canonical_digest(
        {key: value for key, value in rankings.items() if key != "ranking_digest"}
    ):
        raise ValueError("ranking/control artifact digest disagrees")
    ranking_rows = rankings.get("rankings")
    if (
        rankings.get("prediction_ledger_digest") != prediction.ledger_digest
        or rankings.get("response_accessed") is not False
        or not isinstance(ranking_rows, list)
        or tuple(item.get("session_id") for item in ranking_rows) != CAPTURE_IDS
        or artifacts["rankings_and_controls"]["semantic_digest"] != rankings["ranking_digest"]
    ):
        raise ValueError("ranking/control artifact authority disagrees")
    _validate_frozen_rankings_and_controls(
        rankings,
        prediction=prediction,
        inventories=frozen_inventories,
        protocol=protocol,
    )
    return prediction


def _attach_odd(arguments: argparse.Namespace) -> None:
    active_protocol_path = Path(arguments.protocol)
    active_protocol = load_and_validate_final_protocol(
        active_protocol_path,
        repository_root=_REPOSITORY_ROOT,
    )
    output = Path(arguments.output)
    output_receipt = output.with_suffix(".receipt.json")
    if output.exists() or output_receipt.exists():
        raise FileExistsError("odd attachment output or receipt already exists")
    historical_protocol_path, historical_protocol = _load_historical_pre_response_protocol(
        active_protocol
    )
    manifest_path = _REPOSITORY_ROOT / historical_protocol["selector_v2"]["path"]
    manifest = _load_manifest(manifest_path, historical_protocol)
    prediction_path = Path(arguments.prediction_ledger)
    bins_path = Path(arguments.association_bins)
    rankings_path = Path(arguments.rankings)
    receipt_path = Path(arguments.pre_response_receipt)
    _validate_pre_response_bridge_paths(
        active_protocol,
        prediction_path=prediction_path,
        bins_path=bins_path,
        rankings_path=rankings_path,
        receipt_path=receipt_path,
    )
    prediction = _load_pre_response_authority(
        protocol_path=historical_protocol_path,
        protocol=historical_protocol,
        prediction_path=prediction_path,
        bins_path=bins_path,
        rankings_path=rankings_path,
        receipt_path=receipt_path,
    )
    authorities = build_odd_qin_target_authorities(
        manifest,
        prediction,
        residual_half_width_hz=float(active_protocol["odd_response"]["residual_half_width_hz"]),
    )
    if (
        len(authorities) != TARGET_COUNT
        or len({authority.target.identity() for authority in authorities}) != TARGET_COUNT
    ):
        raise ValueError("odd response authority does not contain exactly 5,413 unique targets")
    captures = {item["session_id"]: item for item in active_protocol["captures"]}
    chunks = tuple(
        AuthorizedOddChunk(
            session_id=item["session_id"],
            stream_id=item["stream_id"],
            relative_path=item["relative_path"],
            sample_start=int(item["sample_start"]),
            sample_count=int(item["sample_count"]),
            compressed_sha256=item["compressed_sha256"],
        )
        for item in active_protocol["authorized_odd_chunks"]
    )
    sample_rates = {session: int(item["sample_rate_hz"]) for session, item in captures.items()}
    resolved_chunks = preflight_exact_authorized_odd_chunks(
        authorities=authorities,
        sample_rate_hz_by_session=sample_rates,
        authorized_chunks=chunks,
    )
    if len(resolved_chunks) != TARGET_COUNT:
        raise ValueError("odd chunk preflight did not retain all 5,413 targets")
    # Storage construction is deliberately below every immutable authority,
    # historical bridge, target, and exact-minimal-chunk check above.
    pin = PinnedLocalRoot(Path(arguments.bulk_root))
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(pin)
        source = _PinnedRecordingOddSource(store, chunks)
        adapter = DigestPinnedOddQinAdapter(
            prediction_ledger_digest=prediction.ledger_digest,
            authorities=authorities,
            recording_manifest_sha256_by_session={
                session: item["recording_manifest_sha256"] for session, item in captures.items()
            },
            sample_rate_hz_by_session=sample_rates,
            authorized_chunks=chunks,
            source=source,
            minimum_exact_coherence=float(
                active_protocol["odd_response"]["minimum_exact_coherence"]
            ),
            minimum_coherence_margin=float(
                active_protocol["odd_response"]["minimum_coherence_margin"]
            ),
        )
        attachment = attach_odd_qin_responses_v2(prediction, authorities, adapter)
    finally:
        if store is not None:
            store.close()
        pin.close()
    if attachment.target_count != TARGET_COUNT:
        raise ValueError("odd attachment did not retain all 5,413 targets")
    if (
        attachment.accuracy_eligible_count
        + attachment.boundary_response_count
        + attachment.no_support_response_count
        + attachment.missing_response_count
        != TARGET_COUNT
        or attachment.finite_response_count
        != attachment.accuracy_eligible_count
        + attachment.boundary_response_count
        + attachment.no_support_response_count
    ):
        raise ValueError("odd attachment status denominator does not close")
    attachment_json = attachment.model_dump_json(indent=2) + "\n"
    attachment_sha256 = "sha256:" + hashlib.sha256(attachment_json.encode()).hexdigest()
    pre_response_receipt = _load_json_file(receipt_path)
    receipt_document = {
        "schema": "org.leo.research.final-holdout-odd-attachment-receipt/v2",
        "active_attachment_protocol_sha256": "sha256:" + _sha256(active_protocol_path),
        "active_attachment_protocol_digest": active_protocol["protocol_digest"],
        "historical_pre_response_protocol_sha256": ("sha256:" + _sha256(historical_protocol_path)),
        "historical_pre_response_protocol_digest": historical_protocol["protocol_digest"],
        "pre_response_receipt_sha256": "sha256:" + _sha256(receipt_path),
        "pre_response_receipt_digest": pre_response_receipt["receipt_digest"],
        "prediction_ledger_digest": prediction.ledger_digest,
        "attachment_digest": attachment.attachment_digest,
        "attachment_sha256": attachment_sha256,
        "target_count": attachment.target_count,
        "response_status_counts": {
            "measured_nonmissing": attachment.finite_response_count,
            "accuracy_eligible": attachment.accuracy_eligible_count,
            "boundary": attachment.boundary_response_count,
            "no_support": attachment.no_support_response_count,
            "missing": attachment.missing_response_count,
        },
        "active_authorized_odd_chunks_digest": canonical_digest(
            active_protocol["authorized_odd_chunks"]
        ),
        "historical_authorized_odd_chunks_digest": canonical_digest(
            historical_protocol["authorized_odd_chunks"]
        ),
        "recording_manifest_authority": {
            session: item["recording_manifest_sha256"] for session, item in captures.items()
        },
        "sample_rate_authority_hz": {
            session: item["sample_rate_hz"] for session, item in captures.items()
        },
        "odd_adapter_sha256": "sha256:"
        + _sha256(_REPOSITORY_ROOT / "src/leo/analysis/research/doppler_holdout_odd_adapter.py"),
        "pre_response_artifacts_recomputed_or_mutated": False,
        "prediction_membership_or_values_mutated": False,
    }
    receipt_document["receipt_digest"] = canonical_digest(receipt_document)
    _validate_attachment_receipt_v2(
        receipt_document,
        active_protocol_path=active_protocol_path,
        active_protocol=active_protocol,
        historical_protocol_path=historical_protocol_path,
        historical_protocol=historical_protocol,
        pre_response_receipt_path=receipt_path,
        pre_response_receipt=pre_response_receipt,
        prediction=prediction,
        attachment_sha256=attachment_sha256,
        attachment=attachment,
    )
    with output.open("x") as handle:
        handle.write(attachment_json)
    _write_json_exclusive(output_receipt, receipt_document)


def _score_control_entry(
    entry: dict[str, Any],
    *,
    inventory: FrozenCaptureBinInventory,
    odd_response_by_bin: dict[int, Any],
) -> dict[str, Any]:
    if entry.get("ranking") is None:
        return {
            "control_id": entry.get("control_id"),
            "status": "no_result",
            "rank_one_candidate_id": None,
            "rank_one_training_rms_hz": None,
            "rank_one_heldout_odd_rms_hz": None,
        }
    ranking = _ranking_from_document(entry["ranking"], inventory)
    score = score_frozen_candidate_ranking(
        ranking,
        inventory,
        odd_response_by_bin=odd_response_by_bin,
    )
    rank_one = next(item for item in ranking.fits if item.rank == 1)
    response = next(item for item in score.scores if item.rank == 1)
    return {
        "control_id": entry.get("control_id"),
        "status": "complete",
        "rank_one_candidate_id": rank_one.candidate_id,
        "rank_one_training_rms_hz": rank_one.training_rms_hz,
        "rank_one_heldout_odd_rms_hz": response.heldout_odd_rms_hz,
        "score": _jsonable(asdict(score)),
    }


def _null_p_value(true_value: float | None, controls: list[dict[str, Any]]) -> float | None:
    values = [
        float(item["rank_one_heldout_odd_rms_hz"])
        for item in controls
        if item["rank_one_heldout_odd_rms_hz"] is not None
    ]
    if true_value is None or not values:
        return None
    return (1 + sum(value <= true_value for value in values)) / (len(values) + 1)


def _association_gate(
    *,
    inventory: FrozenCaptureBinInventory,
    primary: FrozenCandidateRanking,
    baseline: FrozenCandidateRanking,
    primary_score: Any,
    controls: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    true_fit = next(item for item in primary.fits if item.rank == 1)
    baseline_fit = next(item for item in baseline.fits if item.rank == 1)
    true_response = next(item for item in primary_score.scores if item.rank == 1)
    training_order = sorted(item.training_rms_hz for item in primary.fits)
    heldout_order = sorted(
        (
            item.heldout_odd_rms_hz,
            item.candidate_id,
        )
        for item in primary_score.scores
        if item.heldout_odd_rms_hz is not None
    )
    training_margin = (
        math.inf if training_order[0] == 0.0 else training_order[1] / training_order[0]
    )
    heldout_rank_one = bool(heldout_order and heldout_order[0][1] == true_fit.candidate_id)
    heldout_margin = None
    if len(heldout_order) >= 2:
        heldout_margin = (
            math.inf if heldout_order[0][0] == 0.0 else heldout_order[1][0] / heldout_order[0][0]
        )
    wrong = controls["wrong_time"]
    permutations = controls["within_track_permutations"]
    wrong_p = _null_p_value(true_response.heldout_odd_rms_hz, wrong)
    permutation_p = _null_p_value(
        true_response.heldout_odd_rms_hz,
        permutations,
    )
    stable_controls = (
        controls["utc_bounds"] + controls["site_sensitivity"] + [controls["predecessor_tle"]]
    )
    stable_complete = [item for item in stable_controls if item["status"] == "complete"]
    rolling_complete = [
        item for item in controls["rolling_origins"] if item["status"] == "complete"
    ]
    evaluation_bin_count = sum(item.split == "evaluation" for item in inventory.bins)
    heldout_available_fraction = (
        true_response.heldout_finite_bin_count / evaluation_bin_count
        if evaluation_bin_count
        else 0.0
    )
    conditions = {
        "recovered_track": primary_score.recovered_track,
        "minimum_heldout_odd_bins": (
            true_response.heldout_finite_bin_count
            >= int(thresholds["minimum_claim_heldout_odd_bins"])
        ),
        "minimum_heldout_odd_bin_fraction": (
            heldout_available_fraction >= float(thresholds["minimum_heldout_odd_bin_fraction"])
        ),
        "absolute_rank_one_heldout_odd_rms": (
            true_response.heldout_odd_rms_hz is not None
            and true_response.heldout_odd_rms_hz
            <= float(thresholds["maximum_claim_rank_one_heldout_odd_rms_hz"])
        ),
        "primary_baseline_rank_one_agreement": (true_fit.candidate_id == baseline_fit.candidate_id),
        "training_runner_margin_ratio": (
            training_margin >= float(thresholds["training_runner_margin_ratio_minimum"])
        ),
        "heldout_rank_one_remains_best": heldout_rank_one,
        "heldout_runner_margin_ratio": (
            heldout_margin is not None
            and heldout_margin >= float(thresholds["heldout_runner_margin_ratio_minimum"])
        ),
        "wrong_time_minimum_scored": sum(
            item["rank_one_heldout_odd_rms_hz"] is not None for item in wrong
        )
        >= int(thresholds["wrong_time_minimum_scored"]),
        "wrong_time_empirical_p": (
            wrong_p is not None and wrong_p <= float(thresholds["null_empirical_p_maximum"])
        ),
        "required_permutations_scored": (
            len(permutations) == int(thresholds["within_track_permutations"])
            and all(item["rank_one_heldout_odd_rms_hz"] is not None for item in permutations)
        ),
        "permutation_empirical_p": (
            permutation_p is not None
            and permutation_p <= float(thresholds["null_empirical_p_maximum"])
        ),
        "utc_site_predecessor_controls_complete_and_stable": (
            len(stable_complete) == len(stable_controls)
            and all(
                item["rank_one_candidate_id"] == true_fit.candidate_id for item in stable_complete
            )
        ),
        "at_least_2_rolling_origins_complete_and_stable": (
            len(rolling_complete) >= int(thresholds["minimum_stable_rolling_origins"])
            and all(
                item["rank_one_candidate_id"] == true_fit.candidate_id for item in rolling_complete
            )
        ),
    }
    compatible = all(conditions.values())
    return {
        "rank_one_candidate_id": true_fit.candidate_id,
        "training_runner_margin_ratio": training_margin,
        "heldout_runner_margin_ratio": heldout_margin,
        "heldout_available_bin_fraction": heldout_available_fraction,
        "wrong_time_empirical_p": wrong_p,
        "permutation_empirical_p": permutation_p,
        "conditions": conditions,
        "recovered_track": primary_score.recovered_track,
        "catalog_compatible": compatible,
        "preset_conditional": compatible,
        "absolute_secure_norad": False,
        "failed_conditions": [key for key, passed in conditions.items() if not passed],
    }


def _validate_attachment_receipt_v2(
    receipt: object,
    *,
    active_protocol_path: Path,
    active_protocol: dict[str, Any],
    historical_protocol_path: Path,
    historical_protocol: dict[str, Any],
    pre_response_receipt_path: Path,
    pre_response_receipt: dict[str, Any],
    prediction: DopplerHoldoutPredictionLedgerV1,
    attachment_sha256: str,
    attachment: OddQinAttachmentLedgerV2,
) -> None:
    """Verify the immutable dual-protocol response receipt before scoring."""

    expected_keys = {
        "schema",
        "active_attachment_protocol_sha256",
        "active_attachment_protocol_digest",
        "historical_pre_response_protocol_sha256",
        "historical_pre_response_protocol_digest",
        "pre_response_receipt_sha256",
        "pre_response_receipt_digest",
        "prediction_ledger_digest",
        "attachment_digest",
        "attachment_sha256",
        "target_count",
        "response_status_counts",
        "active_authorized_odd_chunks_digest",
        "historical_authorized_odd_chunks_digest",
        "recording_manifest_authority",
        "sample_rate_authority_hz",
        "odd_adapter_sha256",
        "pre_response_artifacts_recomputed_or_mutated",
        "prediction_membership_or_values_mutated",
        "receipt_digest",
    }
    capture_authority = {item["session_id"]: item for item in active_protocol["captures"]}
    attachment_status_closed = (
        attachment.accuracy_eligible_count
        + attachment.boundary_response_count
        + attachment.no_support_response_count
        + attachment.missing_response_count
        == TARGET_COUNT
        and attachment.finite_response_count
        == attachment.accuracy_eligible_count
        + attachment.boundary_response_count
        + attachment.no_support_response_count
    )
    if (
        not isinstance(receipt, dict)
        or set(receipt) != expected_keys
        or receipt.get("schema") != "org.leo.research.final-holdout-odd-attachment-receipt/v2"
        or receipt.get("receipt_digest")
        != canonical_digest(
            {key: value for key, value in receipt.items() if key != "receipt_digest"}
        )
        or receipt.get("active_attachment_protocol_sha256")
        != "sha256:" + _sha256(active_protocol_path)
        or receipt.get("active_attachment_protocol_digest") != active_protocol["protocol_digest"]
        or receipt.get("historical_pre_response_protocol_sha256")
        != "sha256:" + _sha256(historical_protocol_path)
        or receipt.get("historical_pre_response_protocol_digest")
        != historical_protocol["protocol_digest"]
        or receipt.get("pre_response_receipt_sha256")
        != "sha256:" + _sha256(pre_response_receipt_path)
        or receipt.get("pre_response_receipt_digest") != pre_response_receipt["receipt_digest"]
        or attachment.target_count != TARGET_COUNT
        or attachment.prediction_ledger_digest != prediction.ledger_digest
        or not attachment_status_closed
        or receipt.get("prediction_ledger_digest") != prediction.ledger_digest
        or receipt.get("attachment_digest") != attachment.attachment_digest
        or receipt.get("attachment_sha256") != attachment_sha256
        or receipt.get("target_count") != TARGET_COUNT
        or receipt.get("response_status_counts")
        != {
            "measured_nonmissing": attachment.finite_response_count,
            "accuracy_eligible": attachment.accuracy_eligible_count,
            "boundary": attachment.boundary_response_count,
            "no_support": attachment.no_support_response_count,
            "missing": attachment.missing_response_count,
        }
        or receipt.get("active_authorized_odd_chunks_digest")
        != canonical_digest(active_protocol["authorized_odd_chunks"])
        or receipt.get("historical_authorized_odd_chunks_digest")
        != canonical_digest(historical_protocol["authorized_odd_chunks"])
        or receipt.get("recording_manifest_authority")
        != {
            session: item["recording_manifest_sha256"]
            for session, item in capture_authority.items()
        }
        or receipt.get("sample_rate_authority_hz")
        != {session: item["sample_rate_hz"] for session, item in capture_authority.items()}
        or receipt.get("odd_adapter_sha256")
        != "sha256:"
        + _sha256(_REPOSITORY_ROOT / "src/leo/analysis/research/doppler_holdout_odd_adapter.py")
        or receipt.get("pre_response_artifacts_recomputed_or_mutated") is not False
        or receipt.get("prediction_membership_or_values_mutated") is not False
    ):
        raise ValueError("odd attachment receipt authority disagrees")


def _report(arguments: argparse.Namespace) -> None:
    active_protocol_path = Path(arguments.protocol)
    protocol = load_and_validate_final_protocol(
        active_protocol_path,
        repository_root=_REPOSITORY_ROOT,
    )
    historical_protocol_path, historical_protocol = _load_historical_pre_response_protocol(protocol)
    prediction_path = Path(arguments.prediction_ledger)
    bins_path = Path(arguments.association_bins)
    rankings_path = Path(arguments.rankings)
    pre_response_receipt_path = Path(arguments.pre_response_receipt)
    _validate_pre_response_bridge_paths(
        protocol,
        prediction_path=prediction_path,
        bins_path=bins_path,
        rankings_path=rankings_path,
        receipt_path=pre_response_receipt_path,
    )
    prediction = _load_pre_response_authority(
        protocol_path=historical_protocol_path,
        protocol=historical_protocol,
        prediction_path=prediction_path,
        bins_path=bins_path,
        rankings_path=rankings_path,
        receipt_path=pre_response_receipt_path,
    )
    attachment_path = Path(arguments.attachment)
    attachment = OddQinAttachmentLedgerV2.model_validate(_load_json_file(attachment_path))
    attachment_receipt_path = Path(arguments.attachment_receipt)
    attachment_receipt = _load_json_file(attachment_receipt_path)
    pre_response_receipt = _load_json_file(pre_response_receipt_path)
    _validate_attachment_receipt_v2(
        attachment_receipt,
        active_protocol_path=active_protocol_path,
        active_protocol=protocol,
        historical_protocol_path=historical_protocol_path,
        historical_protocol=historical_protocol,
        pre_response_receipt_path=pre_response_receipt_path,
        pre_response_receipt=pre_response_receipt,
        prediction=prediction,
        attachment_sha256="sha256:" + _sha256(attachment_path),
        attachment=attachment,
    )
    scores = score_forecasts(prediction, attachment)
    gate = quadratic_promotion_gate(scores)
    denominator_captures: list[dict[str, Any]] = [
        {
            "session_id": item.session_id,
            "target_count": item.denominator_count,
            "accuracy_eligible": item.response_eligible_count,
            "boundary": item.response_boundary_count,
            "no_support": item.response_no_support_count,
            "missing": item.response_missing_count,
            "measured_nonmissing": item.denominator_count - item.response_missing_count,
            "common_accuracy": item.common_accuracy_count,
        }
        for item in scores[0].captures
    ]
    if any(
        item["accuracy_eligible"] + item["boundary"] + item["no_support"] + item["missing"]
        != item["target_count"]
        for item in denominator_captures
    ):
        raise ValueError("per-capture response denominator does not close")
    bins_document = _load_json_file(bins_path)
    inventories = tuple(_inventory_from_document(item) for item in bins_document["inventories"])
    ranking_document = _load_json_file(rankings_path)
    ranking_by_session = {item["session_id"]: item for item in ranking_document["rankings"]}
    captures = {item["session_id"]: item for item in protocol["captures"]}
    association_results: list[dict[str, Any]] = []
    for inventory in inventories:
        raw = ranking_by_session[inventory.session_id]
        if raw.get("evaluable") is not True:
            association_results.append(
                {
                    "session_id": inventory.session_id,
                    "evaluable": False,
                    "failure_reasons": raw["failure_reasons"],
                    "absolute_secure_norad": False,
                }
            )
            continue
        capture = captures[inventory.session_id]
        odd_by_bin = aggregate_odd_responses_to_frozen_bins(
            inventory,
            attachment,
            first_sample_utc_ns=int(capture["first_sample_estimate_utc_ns"]),
            sample_rate_hz=int(capture["sample_rate_hz"]),
        )
        primary = _ranking_from_document(raw["primary"], inventory)
        baseline = _ranking_from_document(raw["baseline"], inventory)
        primary_score = score_frozen_candidate_ranking(
            primary, inventory, odd_response_by_bin=odd_by_bin
        )
        baseline_score = score_frozen_candidate_ranking(
            baseline, inventory, odd_response_by_bin=odd_by_bin
        )
        raw_controls = raw["controls"]
        control_scores: dict[str, Any] = {}
        control_scores["wrong_time"] = [
            _score_control_entry(item, inventory=inventory, odd_response_by_bin=odd_by_bin)
            for item in raw_controls["wrong_time"]
        ]
        control_scores["utc_bounds"] = [
            _score_control_entry(item, inventory=inventory, odd_response_by_bin=odd_by_bin)
            for item in raw_controls["utc_bounds"]
        ]
        control_scores["site_sensitivity"] = [
            _score_control_entry(item, inventory=inventory, odd_response_by_bin=odd_by_bin)
            for item in raw_controls["site_sensitivity"]
        ]
        control_scores["predecessor_tle"] = _score_control_entry(
            raw_controls["predecessor_tle"],
            inventory=inventory,
            odd_response_by_bin=odd_by_bin,
        )
        permutation_scores = []
        for item in raw_controls["within_track_permutations"]:
            control_inventory = _inventory_from_document(item["inventory"])
            permutation_scores.append(
                _score_control_entry(
                    item,
                    inventory=control_inventory,
                    odd_response_by_bin=odd_by_bin,
                )
            )
        control_scores["within_track_permutations"] = permutation_scores
        rolling_scores = []
        for item in raw_controls["rolling_origins"]:
            control_inventory = _inventory_from_document(item["inventory"])
            rolling_scores.append(
                _score_control_entry(
                    item,
                    inventory=control_inventory,
                    odd_response_by_bin=odd_by_bin,
                )
            )
        control_scores["rolling_origins"] = rolling_scores
        association_results.append(
            {
                "session_id": inventory.session_id,
                "evaluable": True,
                "odd_bin_denominator": [_jsonable(asdict(item)) for item in odd_by_bin.values()],
                "primary": _jsonable(asdict(primary_score)),
                "baseline": _jsonable(asdict(baseline_score)),
                "controls": control_scores,
                "gate": _association_gate(
                    inventory=inventory,
                    primary=primary,
                    baseline=baseline,
                    primary_score=primary_score,
                    controls=control_scores,
                    thresholds=protocol["association"],
                ),
            }
        )
    output = {
        "schema": "org.leo.research.final-holdout-score/v1",
        "prediction_ledger_digest": prediction.ledger_digest,
        "attachment_digest": attachment.attachment_digest,
        "primary_metric": protocol["scoring"]["primary_metric"],
        "upstream_conditioning": protocol["upstream_conditioning"],
        "association_thresholds": {
            key: protocol["association"][key]
            for key in (
                "minimum_claim_heldout_odd_bins",
                "minimum_heldout_odd_bin_fraction",
                "maximum_claim_rank_one_heldout_odd_rms_hz",
                "training_runner_margin_ratio_minimum",
                "heldout_runner_margin_ratio_minimum",
                "wrong_time_minimum_scored",
                "null_empirical_p_maximum",
                "minimum_stable_rolling_origins",
            )
        },
        "provenance": {
            "active_attachment_protocol_sha256": "sha256:" + _sha256(active_protocol_path),
            "active_attachment_protocol_digest": protocol["protocol_digest"],
            "historical_pre_response_protocol_sha256": (
                "sha256:" + _sha256(historical_protocol_path)
            ),
            "historical_pre_response_protocol_digest": historical_protocol["protocol_digest"],
            "pre_response_receipt_sha256": "sha256:" + _sha256(pre_response_receipt_path),
            "pre_response_receipt_digest": pre_response_receipt["receipt_digest"],
            "attachment_receipt_sha256": "sha256:" + _sha256(attachment_receipt_path),
            "attachment_receipt_digest": attachment_receipt["receipt_digest"],
        },
        "response_status_denominator": {
            "target_count": TARGET_COUNT,
            "measured_nonmissing": attachment.finite_response_count,
            "accuracy_eligible": attachment.accuracy_eligible_count,
            "boundary": attachment.boundary_response_count,
            "no_support": attachment.no_support_response_count,
            "missing": attachment.missing_response_count,
            "common_accuracy": scores[0].common_accuracy_count,
            "captures": denominator_captures,
        },
        "scores": [_jsonable(asdict(item)) for item in scores],
        "quadratic_promotion_gate": _jsonable(asdict(gate)),
        "association": association_results,
        "shared_physical_radio_rate_sensitivity": ranking_document[
            "shared_physical_radio_rate_sensitivity"
        ],
        "calibrated_interval_scoring": protocol["calibrated_intervals"],
        "absolute_secure_norad": False,
    }
    output["score_digest"] = canonical_digest(output)
    score_path = Path(arguments.output)
    _write_json(score_path, output)
    _write_report_artifacts(
        output,
        figure_dir=Path(arguments.figure_dir),
        markdown_path=Path(arguments.markdown),
        score_path=score_path,
        protocol_path=active_protocol_path,
    )


def _write_report_artifacts(
    score: dict[str, Any],
    *,
    figure_dir: Path,
    markdown_path: Path,
    score_path: Path,
    protocol_path: Path,
) -> None:
    """Render only plain Matplotlib PNGs and a provenance-linked report."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure_dir.mkdir(parents=True, exist_ok=False)
    methods = score["scores"]
    labels = [item["method"] for item in methods]
    rms = [item["equal_capture_rms_hz"] for item in methods]
    figure, axis = plt.subplots(figsize=(10, 5.5))
    axis.bar(labels, [np.nan if item is None else item for item in rms], color="#4477aa")
    axis.set_ylabel("Equal-capture downstream-withheld odd-Qin CFO RMS (Hz)")
    axis.set_title("Strict-past holdout forecast comparison (upstream-conditioned)")
    axis.tick_params(axis="x", rotation=20)
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    forecast_path = figure_dir / "forecast-method-rms.png"
    figure.savefig(forecast_path, dpi=180)
    plt.close(figure)

    by_method = {item["method"]: item for item in methods}
    primary = by_method[PRIMARY_ASSOCIATION_METHOD]
    baseline = by_method[BASELINE_ASSOCIATION_METHOD]
    capture_labels = [item["session_id"].split("T", 1)[-1][:6] for item in primary["captures"]]
    x = np.arange(len(capture_labels))
    figure, axis = plt.subplots(figsize=(12, 5.5))
    axis.plot(
        x,
        [item["rms_hz"] for item in baseline["captures"]],
        marker="o",
        label="fixed 500 ms linear",
    )
    axis.plot(
        x,
        [item["rms_hz"] for item in primary["captures"]],
        marker="o",
        label="strict-past 500 ms quadratic",
    )
    axis.set_xticks(x, capture_labels, rotation=30)
    axis.set_ylabel("Downstream-withheld odd-Qin CFO RMS (Hz)")
    axis.set_title("Paired per-capture forecast error (upstream-conditioned)")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    capture_path = figure_dir / "paired-capture-rms.png"
    figure.savefig(capture_path, dpi=180)
    plt.close(figure)

    association = score["association"]
    association_labels = [item["session_id"].split("T", 1)[-1][:6] for item in association]
    association_rms = []
    colors = []
    for item in association:
        if not item["evaluable"]:
            association_rms.append(np.nan)
            colors.append("#bbbbbb")
            continue
        rank_one = next(row for row in item["primary"]["scores"] if row["rank"] == 1)
        association_rms.append(rank_one["heldout_odd_rms_hz"])
        colors.append("#228833" if item["gate"]["catalog_compatible"] else "#cc6677")
    figure, axis = plt.subplots(figsize=(12, 5.5))
    axis.bar(association_labels, association_rms, color=colors)
    absolute_gate_hz = score["association_thresholds"]["maximum_claim_rank_one_heldout_odd_rms_hz"]
    axis.axhline(
        absolute_gate_hz,
        color="black",
        linestyle="--",
        linewidth=1,
        label=f"{absolute_gate_hz:g} Hz gate",
    )
    axis.set_ylabel("Frozen rank-one held-out odd RMS (Hz)")
    axis.set_title("Starlink association: preset-conditional gate outcome")
    axis.tick_params(axis="x", rotation=30)
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    figure.tight_layout()
    association_path = figure_dir / "association-heldout-rms.png"
    figure.savefig(association_path, dpi=180)
    plt.close(figure)

    forecast_link = Path(os.path.relpath(forecast_path, markdown_path.parent)).as_posix()
    capture_link = Path(os.path.relpath(capture_path, markdown_path.parent)).as_posix()
    association_link = Path(os.path.relpath(association_path, markdown_path.parent)).as_posix()
    denominator = score["response_status_denominator"]
    denominator_rows = "\n".join(
        "| {session_id} | {target_count} | {accuracy_eligible} | {boundary} | "
        "{no_support} | {missing} | {common_accuracy} |".format(**item)
        for item in denominator["captures"]
    )

    gate = score["quadratic_promotion_gate"]
    report = f"""# Final POST-FIX Doppler holdout and Starlink association

This report was generated from the immutable score ledger `{score_path.name}` under
the prospectively frozen protocol `{protocol_path.name}`. Every one of the 5,413
selector-v2 targets remains in the denominator.

**Conditioning boundary:** the downstream predictor fit and score withheld odd-Qin,
but the frozen upstream Standard source, alias, trajectory, and frame-epoch products
may use all-Qin GLRT64 evidence. Every result here is therefore **conditional on
frozen upstream all-Qin acquisition and conditioning**, not an end-to-end unopened
acquisition result. The primary metric is equal-capture downstream-withheld odd-Qin
CFO RMS on the one common eligible mask.

## Forecast result

- Quadratic promotion gate: **{"PASS" if gate["passed"] else "FAIL / ABSTAIN"}**.
- Equal-capture RMS ratio (quadratic / fixed 500 ms): `{gate["ratio"]}`.
- Capture wins: `{gate["capture_wins"]}` of 10; comparisons: `{gate["capture_comparisons"]}`.
- Failed conditions: `{", ".join(gate["failed_conditions"]) or "none"}`.

![Strict-past method comparison]({forecast_link})

![Paired capture errors]({capture_link})

## Response denominator

| Capture | Targets | Eligible | Boundary | No support | Missing | Common accuracy |
|---|---:|---:|---:|---:|---:|---:|
{denominator_rows}

Global totals: targets `{denominator["target_count"]}`, measured nonmissing
`{denominator["measured_nonmissing"]}`, eligible `{denominator["accuracy_eligible"]}`,
boundary `{denominator["boundary"]}`, no support `{denominator["no_support"]}`, missing
`{denominator["missing"]}`, common accuracy `{denominator["common_accuracy"]}`.

## Starlink association

All candidate identities, constant offsets, controls, and nuisance selections were
frozen before odd-Qin access. The primary lane uses the strict-past quadratic
predictor; fixed 500 ms is the mandatory agreement baseline. Wrong-time,
within-track permutation, rolling-origin, UTC-bound, site, and predecessor-TLE
controls are retained in the score ledger. The observer site is a reviewed preset,
not capture-bound, so absolute secure NORAD identification is forced **false**.

![Held-out association RMS]({association_link})

## Interval calibration

The corrected fixed-500 calibration point estimator failed its frozen point-RMSE
gate, and the requested formal 95% group quantile was unavailable. The protocol
therefore carries calibrated intervals only as a fail-closed abstention; no
post-hoc interval claim is made here.

## Provenance

- Score digest: `{score["score_digest"]}`
- Prediction ledger digest: `{score["prediction_ledger_digest"]}`
- Odd attachment digest: `{score["attachment_digest"]}`
- Absolute secure NORAD: `false`
"""
    markdown_path.write_text(report)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_before_deadline(deadline_monotonic: float) -> None:
    if time.monotonic() > deadline_monotonic:
        raise RuntimeError("pre-response propagation/ranking exceeded its frozen compute limit")


def _load_json_file(path: Path) -> Any:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key in {path.name}: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def _jsonable(value: object) -> object:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _write_json(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


def _write_json_exclusive(path: Path, document: object) -> None:
    with path.open("x") as handle:
        handle.write(json.dumps(document, indent=2, sort_keys=True) + "\n")


def _write_predict_failure_status(
    arguments: argparse.Namespace,
    *,
    started_time_ns: int,
    error: BaseException,
    traceback_text: str,
) -> None:
    """Persist a fail-closed status without overwriting any partial ledger."""

    output = Path(arguments.output_dir)
    if not getattr(arguments, "_output_dir_created_by_run", False) or not output.is_dir():
        return
    path = output / "pre-response-failure-status.json"
    if path.exists():
        return
    artifacts: dict[str, dict[str, object]] = {}
    for basename in (
        "prediction-ledger.json",
        "association-bin-inventory.json",
        "pre-response-rankings.json",
        "pre-response-receipt.json",
    ):
        artifact = output / basename
        if artifact.is_file():
            artifacts[basename] = {
                "byte_size": artifact.stat().st_size,
                "sha256": "sha256:" + _sha256(artifact),
            }
    protocol_path = Path(arguments.protocol)
    document = {
        "schema": "org.leo.research.final-holdout-pre-response-failure-status/v1",
        "status": "failed_closed",
        "started_time_ns": started_time_ns,
        "completed_time_ns": time.time_ns(),
        "command_argv": list(sys.argv),
        "cwd": os.getcwd(),
        "protocol_path": str(protocol_path),
        "protocol_sha256": (
            "sha256:" + _sha256(protocol_path) if protocol_path.is_file() else None
        ),
        "exception_type": type(error).__name__,
        "exception_message": str(error),
        "traceback": traceback_text,
        "candidate_propagation_or_ranking_may_have_started": bool(
            getattr(arguments, "_candidate_work_started", False)
        ),
        "odd_iq_accessed": False,
        "odd_responses_accessed": False,
        "partial_artifacts": artifacts,
    }
    document["status_digest"] = canonical_digest(document)
    _write_json(path, document)


def _validate_pre_response_replay_artifacts(
    protocol: dict[str, Any],
    *,
    prediction: DopplerHoldoutPredictionLedgerV1,
    prediction_path: Path,
    bins_document: dict[str, Any],
    bins_path: Path,
) -> None:
    correction = protocol["supersession"]["response_free_correction"]
    if prediction.ledger_digest != correction["expected_prediction_ledger_digest"]:
        raise ValueError("prediction ledger semantic digest differs from the response-free replay")
    if "sha256:" + _sha256(prediction_path) != correction["expected_prediction_ledger_sha256"]:
        raise ValueError("prediction ledger bytes differ from the response-free replay")
    if bins_document["bins_digest"] != correction["expected_corrected_bins_digest"]:
        raise ValueError("corrected association-bin digest differs from the response-free replay")
    if "sha256:" + _sha256(bins_path) != correction["expected_corrected_bins_sha256"]:
        raise ValueError("corrected association-bin bytes differ from the response-free replay")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="stage", required=True)
    predict = subparsers.add_parser("predict")
    predict.add_argument("--protocol", required=True)
    predict.add_argument("--output-dir", required=True)
    attach = subparsers.add_parser("attach-odd")
    attach.add_argument("--protocol", required=True)
    attach.add_argument("--prediction-ledger", required=True)
    attach.add_argument("--association-bins", required=True)
    attach.add_argument("--rankings", required=True)
    attach.add_argument("--pre-response-receipt", required=True)
    attach.add_argument("--bulk-root", default="/srv/bulk/leo")
    attach.add_argument("--output", required=True)
    report = subparsers.add_parser("report")
    report.add_argument("--protocol", required=True)
    report.add_argument("--prediction-ledger", required=True)
    report.add_argument("--association-bins", required=True)
    report.add_argument("--rankings", required=True)
    report.add_argument("--pre-response-receipt", required=True)
    report.add_argument("--attachment", required=True)
    report.add_argument("--attachment-receipt", required=True)
    report.add_argument("--output", required=True)
    report.add_argument("--figure-dir", required=True)
    report.add_argument("--markdown", required=True)
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    if arguments.stage == "predict":
        arguments._candidate_work_started = False
        arguments._output_dir_created_by_run = False
        started_time_ns = time.time_ns()
        try:
            _predict(arguments)
        except BaseException as error:
            try:
                _write_predict_failure_status(
                    arguments,
                    started_time_ns=started_time_ns,
                    error=error,
                    traceback_text=traceback.format_exc(),
                )
            except Exception as status_error:
                print(
                    f"unable to persist pre-response failure status: {status_error}",
                    file=sys.stderr,
                )
            raise
    elif arguments.stage == "attach-odd":
        _attach_odd(arguments)
    else:
        _report(arguments)


if __name__ == "__main__":
    main()
