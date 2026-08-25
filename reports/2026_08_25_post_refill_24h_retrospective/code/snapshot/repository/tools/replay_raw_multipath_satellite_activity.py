#!/usr/bin/env python3
"""Replay raw PilotScanV3 evidence jointly across two to four receiver paths.

This research adapter consumes complete duration-assignment inputs from one
recording, maps their scheduled probes onto one explicit absolute-UTC 100-ms
grid, and searches an explicit two- or three-object catalogue shortlist.  One
orbital-time delay is shared by all paths for a catalogue object.  Constant
CFO offsets are proposed and fixed independently per path.

An optional digest-bound eligibility plan can declare, independently for each
catalogue object and receiver path, the 100-ms cells in which that RF path is
eligible to carry the transmitter.  Eligibility is fixed before decoding and
is never inferred from the scored peaks.

The result is exact only for each evaluated fixed nuisance-state tuple and for
the retained, bounded state bank.  The shortlist and CFO modes are supplied or
proposed from the evaluated data; this is not catalogue search, orbit
estimation, payload decoding, or spacecraft identification.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import itertools
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from leo.analysis.research.joint_multipath_satellite_activity import (  # type: ignore[import-untyped]
    decode_joint_fixed_multipath_satellites,
)
from leo.analysis.research.multipath_satellite_activity import (  # type: ignore[import-untyped]
    FixedMultipathSatelliteHypothesis,
    MultipathSatelliteActivityProblem,
    ReceiverPathActivityEvidence,
    ReceiverPathFixedHypothesis,
    decode_fixed_multipath_satellite,
)
from leo.analysis.research.satellite_activity import (  # type: ignore[import-untyped]
    ActivityGrid,
    AssociationCostModel,
    CfoProbe,
    PredictedProbeCfo,
)
from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]
from leo.contracts.sky import ObserverSiteV1  # type: ignore[import-untyped]
from leo.sky.propagation import parse_element_sets  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools import replay_raw_grouped_satellite_activity as raw_replay  # noqa: E402
from tools.replay_joint_fixed_satellite_activity import (  # noqa: E402
    INPUT_SCHEMA,
    _doppler_curve,
    _file_digest,
    _ordered_schedule,
    _read_json,
    _refuse_qnap_output,
    _unique_satellite_index,
)

OUTPUT_SCHEMA = "org.leo.research.raw-multipath-satellite-activity-replay/v2"
ELIGIBILITY_PLAN_SCHEMA = "org.leo.research.multipath-rf-eligibility-plan/v1"
ALGORITHM = "bounded-retained-state-raw-multipath-satellite-activity-v2"
FIXED_JOINT_ALGORITHM = "bounded-exact-fixed-nuisance-joint-multipath-semimarkov-v2"
UTC_CELL_NS = 100_000_000
MINIMUM_PATH_COUNT = 2
MAXIMUM_PATH_COUNT = 4

_IMPLEMENTATION_FILE_PATHS = (
    "tools/replay_raw_multipath_satellite_activity.py",
    "tools/replay_raw_grouped_satellite_activity.py",
    "tools/replay_joint_fixed_satellite_activity.py",
    "src/leo/analysis/research/joint_multipath_satellite_activity.py",
    "src/leo/analysis/research/multipath_satellite_activity.py",
    "src/leo/analysis/research/multi_satellite_activity.py",
    "src/leo/analysis/research/grouped_satellite_activity.py",
    "src/leo/analysis/research/satellite_activity.py",
    "src/leo/analysis/research/satellite_activity_scores.py",
    "src/leo/sky/doppler.py",
    "src/leo/sky/frames.py",
    "src/leo/sky/propagation.py",
    "src/leo/sky/sampling.py",
    "src/leo/sky/screening.py",
    "src/leo/contracts/base.py",
    "src/leo/contracts/digests.py",
    "src/leo/contracts/sky.py",
    "pyproject.toml",
    "uv.lock",
)


def _finite(value: float, label: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _canonical_sha256(value: str, label: str) -> str:
    digest = value if value.startswith("sha256:") else f"sha256:{value}"
    if len(digest) != 71 or any(character not in "0123456789abcdef" for character in digest[7:]):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _implementation_file_digests() -> dict[str, str]:
    """Bind the result-changing adapter, solver, geometry, and lockfile surface."""

    return {
        relative_path: _file_digest(REPOSITORY_ROOT / relative_path)
        for relative_path in _IMPLEMENTATION_FILE_PATHS
    }


def _runtime_versions() -> dict[str, str]:
    """Record numerical runtime versions that can change replay output."""

    return {
        "python": ".".join(str(item) for item in sys.version_info[:3]),
        "numpy": np.__version__,
        "sgp4": importlib.metadata.version("sgp4"),
    }


@dataclass(frozen=True, slots=True)
class MultipathReplayConfig(raw_replay.RawReplayConfig):
    """Raw-score, nuisance-search, and bounded Cartesian settings."""

    maximum_path_offset_combinations_per_delay: int = 64

    def __post_init__(self) -> None:
        raw_replay.RawReplayConfig.__post_init__(self)
        _positive_integer(
            self.maximum_path_offset_combinations_per_delay,
            "maximum path-offset combinations per delay",
        )
        if not math.isclose(self.cell_duration_s, 0.1, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("multipath replay requires exact 100-ms activity cells")
        if self.minimum_active_duration_s + 1e-12 < 0.5:
            raise ValueError("multipath replay requires activity runs of at least 0.5 seconds")
        if self.allow_left_censored or self.allow_right_censored:
            raise ValueError("multipath replay does not permit boundary-censored short runs")


@dataclass(frozen=True, slots=True)
class _ProbeUtc:
    probe_id: str
    estimate_utc_ns: int
    earliest_utc_ns: int
    latest_utc_ns: int
    cell_index: int
    usable: bool
    retained_candidate_count: int

    @property
    def crosses_cell_boundary(self) -> bool:
        return self.earliest_utc_ns // UTC_CELL_NS != self.latest_utc_ns // UTC_CELL_NS


@dataclass(frozen=True, slots=True)
class _PathContext:
    path_id: str
    dataset: dict[str, Any]
    dataset_path: Path
    dataset_digest: str
    scan_content_digest: str
    window_rows: tuple[dict[str, Any], ...]
    probe_utc: tuple[_ProbeUtc, ...]
    inventory: Any


@dataclass(frozen=True, slots=True)
class _PathModeState:
    path_id: str
    cfo_offset_hz: float
    support_group_count: int
    support_probe_count: int
    minimum_elevation_deg: float
    maximum_elevation_deg: float
    predictions_hz: tuple[float, ...]
    eligible_by_cell: tuple[bool, ...]


@dataclass(frozen=True, slots=True)
class _StateEvaluation:
    hypothesis: FixedMultipathSatelliteHypothesis
    paths: tuple[_PathModeState, ...]
    single_total_cost: float
    single_delta_from_null: float
    single_selected: bool


@dataclass(frozen=True, slots=True)
class _CatalogBank:
    generated: tuple[_StateEvaluation, ...]
    retained: tuple[_StateEvaluation, ...]
    possible_path_offset_combination_count: int
    evaluated_path_offset_combination_count: int
    path_offset_cartesian_exhausted: bool


@dataclass(frozen=True, slots=True)
class _JointEvaluation:
    hypotheses: tuple[FixedMultipathSatelliteHypothesis, ...]
    result: Any


@dataclass(frozen=True, slots=True)
class _EligibilityBinding:
    by_catalog_path: dict[int, dict[str, tuple[bool, ...]]]
    receipt: dict[str, Any]
    supplied: bool
    plan_path: Path | None
    plan_file_digest: str | None


def _eligible_cell_runs(mask: tuple[bool, ...]) -> list[list[int]]:
    runs = []
    index = 0
    while index < len(mask):
        if not mask[index]:
            index += 1
            continue
        start = index
        while index + 1 < len(mask) and mask[index + 1]:
            index += 1
        runs.append([start, index + 1])
        index += 1
    return runs


def _mask_from_cell_runs(
    raw_runs: object,
    *,
    cell_count: int,
    label: str,
) -> tuple[bool, ...]:
    if not isinstance(raw_runs, list):
        raise ValueError(f"{label} eligible-cell runs must be a list")
    mask = [False] * cell_count
    previous_end = -1
    for raw_run in raw_runs:
        if (
            not isinstance(raw_run, list)
            or len(raw_run) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) for value in raw_run)
        ):
            raise ValueError(f"{label} eligible-cell runs must contain integer [start, end) pairs")
        start, end = raw_run
        if not 0 <= start < end <= cell_count:
            raise ValueError(f"{label} eligible-cell run lies outside the replay grid")
        if start <= previous_end:
            raise ValueError(f"{label} eligible-cell runs must be sorted, disjoint, and coalesced")
        for cell_index in range(start, end):
            mask[cell_index] = True
        previous_end = end
    return tuple(mask)


def _eligibility_binding(
    *,
    document: dict[str, Any] | None,
    plan_path: Path | None,
    expected_plan_digest: str | None,
    catalog_numbers: tuple[int, ...],
    path_ids: tuple[str, ...],
    start_utc_ns: int,
    end_utc_ns: int,
) -> _EligibilityBinding:
    cell_count = (end_utc_ns - start_utc_ns) // UTC_CELL_NS
    supplied_values = (
        document is not None,
        plan_path is not None,
        expected_plan_digest is not None,
    )
    if any(supplied_values) and not all(supplied_values):
        raise ValueError(
            "eligibility plan document, path, and expected digest must be supplied together"
        )
    ordered_catalogs = tuple(sorted(catalog_numbers))
    ordered_paths = tuple(sorted(path_ids))
    if document is None:
        by_catalog_path = {
            catalog_number: {path_id: (True,) * cell_count for path_id in ordered_paths}
            for catalog_number in ordered_catalogs
        }
        receipt = {
            "mode": "implicit-all-cells-eligible-v1",
            "plan_schema": None,
            "plan_file_digest": None,
            "plan_content_digest": None,
            "basis": "adapter default: every supplied path is RF-eligible in every cell",
            "adapter_inferred_from_scored_observations": False,
            "window": {
                "start_utc_ns": start_utc_ns,
                "end_utc_ns": end_utc_ns,
                "cell_duration_ns": UTC_CELL_NS,
                "cell_count": cell_count,
            },
            "catalogs": [
                {
                    "catalog_number": catalog_number,
                    "paths": [
                        {
                            "path_id": path_id,
                            "eligible_cell_runs": [[0, cell_count]],
                            "eligible_cell_count": cell_count,
                        }
                        for path_id in ordered_paths
                    ],
                }
                for catalog_number in ordered_catalogs
            ],
        }
        return _EligibilityBinding(by_catalog_path, receipt, False, None, None)

    assert plan_path is not None and expected_plan_digest is not None
    observed_digest = _file_digest(plan_path)
    if observed_digest != _canonical_sha256(expected_plan_digest, "eligibility-plan digest"):
        raise ValueError("eligibility-plan file digest mismatch")
    if document != _read_json(plan_path):
        raise ValueError("eligibility-plan document does not match its digest-bound file")
    if document.get("schema") != ELIGIBILITY_PLAN_SCHEMA:
        raise ValueError(f"expected eligibility-plan schema {ELIGIBILITY_PLAN_SCHEMA}")
    basis = document.get("basis")
    if not isinstance(basis, str) or not basis:
        raise ValueError("eligibility plan needs a nonempty basis")
    window = document.get("window")
    expected_window = {
        "start_utc_ns": start_utc_ns,
        "end_utc_ns": end_utc_ns,
        "cell_duration_ns": UTC_CELL_NS,
        "cell_count": cell_count,
    }
    if window != expected_window:
        raise ValueError("eligibility-plan window differs from the replay grid")
    raw_catalogs = document.get("catalogs")
    if not isinstance(raw_catalogs, list):
        raise ValueError("eligibility plan needs a catalogue list")
    raw_catalog_by_number: dict[int, dict[str, Any]] = {}
    for raw_catalog in raw_catalogs:
        if not isinstance(raw_catalog, dict):
            raise ValueError("eligibility-plan catalogue entry is not an object")
        catalog_number = raw_catalog.get("catalog_number")
        if isinstance(catalog_number, bool) or not isinstance(catalog_number, int):
            raise ValueError("eligibility-plan catalogue number must be an integer")
        if catalog_number in raw_catalog_by_number:
            raise ValueError("eligibility plan repeats a catalogue number")
        raw_catalog_by_number[catalog_number] = raw_catalog
    if set(raw_catalog_by_number) != set(ordered_catalogs):
        raise ValueError("eligibility-plan catalogues differ from the replay shortlist")

    by_catalog_path = {}
    receipt_catalogs = []
    for catalog_number in ordered_catalogs:
        raw_paths = raw_catalog_by_number[catalog_number].get("paths")
        if not isinstance(raw_paths, list):
            raise ValueError("eligibility-plan catalogue needs a path list")
        raw_path_by_id: dict[str, dict[str, Any]] = {}
        for raw_path in raw_paths:
            if not isinstance(raw_path, dict):
                raise ValueError("eligibility-plan path entry is not an object")
            path_id = raw_path.get("path_id")
            if not isinstance(path_id, str) or not path_id:
                raise ValueError("eligibility-plan path ID must be a nonempty string")
            if path_id in raw_path_by_id:
                raise ValueError("eligibility plan repeats a receiver path")
            raw_path_by_id[path_id] = raw_path
        if set(raw_path_by_id) != set(ordered_paths):
            raise ValueError(
                f"eligibility-plan paths for NORAD {catalog_number} differ from replay paths"
            )
        catalog_masks = {}
        receipt_paths = []
        for path_id in ordered_paths:
            mask = _mask_from_cell_runs(
                raw_path_by_id[path_id].get("eligible_cell_runs"),
                cell_count=cell_count,
                label=f"NORAD {catalog_number} path {path_id!r}",
            )
            catalog_masks[path_id] = mask
            receipt_paths.append(
                {
                    "path_id": path_id,
                    "eligible_cell_runs": _eligible_cell_runs(mask),
                    "eligible_cell_count": sum(mask),
                }
            )
        by_catalog_path[catalog_number] = catalog_masks
        receipt_catalogs.append({"catalog_number": catalog_number, "paths": receipt_paths})
    receipt = {
        "mode": "explicit-fixed-path-cell-runs-v1",
        "plan_schema": ELIGIBILITY_PLAN_SCHEMA,
        "plan_file_digest": observed_digest,
        "plan_content_digest": canonical_digest(document),
        "basis": basis,
        "adapter_inferred_from_scored_observations": False,
        "window": expected_window,
        "catalogs": receipt_catalogs,
    }
    return _EligibilityBinding(
        by_catalog_path=by_catalog_path,
        receipt=receipt,
        supplied=True,
        plan_path=plan_path.resolve(),
        plan_file_digest=observed_digest,
    )


def _interpolated_utc(
    timing: dict[str, Any], sample: int, declared_sample_count: int
) -> dict[str, int]:
    last_sample = declared_sample_count - 1
    if not 0 <= sample <= last_sample:
        raise ValueError("scheduled probe sample lies outside the declared capture")

    def interpolate(prefix: str) -> int:
        first = int(timing[f"first_{prefix}_utc_ns"])
        last = int(timing[f"last_{prefix}_utc_ns"])
        if last < first:
            raise ValueError("duration-input timing anchors are not increasing")
        return first + round((last - first) * sample / last_sample)

    result = {
        "earliest_utc_ns": interpolate("earliest"),
        "estimate_utc_ns": interpolate("estimate"),
        "latest_utc_ns": interpolate("latest"),
    }
    if not result["earliest_utc_ns"] <= result["estimate_utc_ns"] <= result["latest_utc_ns"]:
        raise ValueError("interpolated UTC estimate lies outside its timing interval")
    return result


def _absolute_window_rows(
    dataset: dict[str, Any],
    *,
    start_utc_ns: int,
    end_utc_ns: int,
) -> tuple[tuple[dict[str, Any], ...], tuple[_ProbeUtc, ...]]:
    timing = dataset.get("timing_binding")
    if not isinstance(timing, dict):
        raise ValueError("duration input omits timing binding")
    if (
        timing.get("observation_utc_method")
        != ("linear interpolation between manifest first/last sample timing anchors")
        or timing.get("receiver_relative_time_origin") != "first captured sample"
    ):
        raise ValueError("duration input has unsupported probe UTC authority")
    capture = dataset["capture"]
    sample_rate_hz = int(capture["sample_rate_hz"])
    declared_sample_count = int(capture["declared_sample_count"])
    if declared_sample_count < 2:
        raise ValueError("duration input capture is too short for UTC interpolation")
    ordered = _ordered_schedule(dataset)
    selected_rows = []
    selected_utc = []
    for row in ordered:
        sample_start = int(row["probe_sample_start"])
        expected_relative_s = sample_start / sample_rate_hz
        if not math.isclose(
            float(row["probe_start_time_s"]),
            expected_relative_s,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("scheduled probe time disagrees with its sample start")
        expected_utc = _interpolated_utc(timing, sample_start, declared_sample_count)
        persisted_utc = row.get("probe_start_utc")
        if not isinstance(persisted_utc, dict) or any(
            int(persisted_utc.get(label, -1)) != expected
            for label, expected in expected_utc.items()
        ):
            raise ValueError("scheduled probe UTC disagrees with persisted timing anchors")
        estimate = expected_utc["estimate_utc_ns"]
        if not start_utc_ns <= estimate < end_utc_ns:
            continue
        cell_index = (estimate - start_utc_ns) // UTC_CELL_NS
        selected_rows.append(row)
        selected_utc.append(
            _ProbeUtc(
                probe_id=str(row["probe_id"]),
                estimate_utc_ns=estimate,
                earliest_utc_ns=expected_utc["earliest_utc_ns"],
                latest_utc_ns=expected_utc["latest_utc_ns"],
                cell_index=cell_index,
                usable=bool(row["usable_for_activity"]),
                retained_candidate_count=int(row["retained_candidate_count"]),
            )
        )
    if len(selected_rows) < 2:
        raise ValueError("each receiver path needs at least two scheduled probes in the UTC window")
    return tuple(selected_rows), tuple(selected_utc)


def _path_identity(dataset: dict[str, Any]) -> tuple[str, tuple[object, ...]]:
    capture = dataset.get("capture")
    frequency = dataset.get("frequency_binding")
    if not isinstance(capture, dict) or not isinstance(frequency, dict):
        raise ValueError("duration input omits capture or frequency binding")
    identity = (
        str(capture.get("radio_serial", "")),
        int(capture["receiver_id"]),
        str(capture.get("stream_id", "")),
        str(frequency.get("tuning_tag", "")),
    )
    if not identity[0] or not identity[2] or not identity[3]:
        raise ValueError("duration input has an incomplete receiver-path identity")
    path_id = f"{capture.get('radio_id', identity[0])}:rx{identity[1]}:{identity[2]}:{identity[3]}"
    return path_id, identity


def _calibration_source_digests(document: dict[str, Any]) -> set[str]:
    sources = document.get("sources")
    result: set[str] = set()
    if not isinstance(sources, dict):
        return result
    for item in sources.get("null", ()):
        if isinstance(item, dict):
            result.add(str(item.get("file_digest", "")))
    for item in sources.get("signal", ()):
        if isinstance(item, dict) and isinstance(item.get("pilot_scan"), dict):
            result.add(str(item["pilot_scan"].get("file_digest", "")))
    return result


def _validate_raw_duration_input(dataset: dict[str, Any]) -> None:
    """Validate only lineage used by raw replay, not unrelated frame products."""

    if dataset.get("schema") != INPUT_SCHEMA:
        raise ValueError(f"expected input schema {INPUT_SCHEMA}")
    if dataset.get("per_probe_rows_omitted"):
        raise ValueError("raw multipath replay requires the full scheduled-probe extraction")
    scheduled = dataset.get("scheduled_probes")
    if not isinstance(scheduled, list) or not scheduled:
        raise ValueError("duration input has no scheduled-probe inventory")
    if any(int(item.get("truncated_candidate_count", 0)) != 0 for item in scheduled):
        raise ValueError("raw multipath replay refuses truncated scheduled candidates")
    if not isinstance(dataset.get("capture"), dict):
        raise ValueError("duration input omits capture binding")


def _load_path_contexts(
    *,
    dataset_paths: tuple[Path, ...],
    expected_dataset_digests: tuple[str, ...],
    calibration: Any,
    calibration_document: dict[str, Any],
    start_utc_ns: int,
    end_utc_ns: int,
    config: MultipathReplayConfig,
) -> tuple[_PathContext, ...]:
    if not MINIMUM_PATH_COUNT <= len(dataset_paths) <= MAXIMUM_PATH_COUNT:
        raise ValueError("multipath replay requires two to four duration-input paths")
    if len(expected_dataset_digests) != len(dataset_paths):
        raise ValueError("every duration input needs one expected digest")
    contexts = []
    path_identities: set[tuple[object, ...]] = set()
    scan_file_digests: set[str] = set()
    scan_content_digests: set[str] = set()
    session_ids: set[str] = set()
    manifest_digests: set[str] = set()
    calibration_sources = _calibration_source_digests(calibration_document)
    for path, expected_digest in zip(dataset_paths, expected_dataset_digests, strict=True):
        observed_digest = _file_digest(path)
        if observed_digest != _canonical_sha256(expected_digest, "duration-input digest"):
            raise ValueError(f"duration-input digest mismatch: {path}")
        dataset = _read_json(path)
        _validate_raw_duration_input(dataset)
        path_id, identity = _path_identity(dataset)
        if identity in path_identities:
            raise ValueError("duration inputs repeat one receiver-path identity")
        path_identities.add(identity)
        capture = dataset["capture"]
        session_ids.add(str(capture.get("session_id", "")))
        manifest_digests.add(
            _canonical_sha256(
                str(capture.get("recording_manifest_digest", "")),
                "recording-manifest digest",
            )
        )

        rows, probe_utc = _absolute_window_rows(
            dataset,
            start_utc_ns=start_utc_ns,
            end_utc_ns=end_utc_ns,
        )
        source_products = dataset.get("source_products")
        if not isinstance(source_products, dict) or not isinstance(
            source_products.get("scan"), dict
        ):
            raise ValueError("duration input omits raw scan lineage")
        scan_path = Path(str(source_products["scan"]["path"]))
        scan_file_digest = _file_digest(scan_path)
        if scan_file_digest != str(source_products["scan"]["file_digest"]):
            raise ValueError("duration-input scan file digest mismatch")
        scan_content_digest = canonical_digest(_read_json(scan_path))
        if scan_file_digest in scan_file_digests or scan_content_digest in scan_content_digests:
            raise ValueError("duration inputs repeat one raw pilot-scan identity")
        scan_file_digests.add(scan_file_digest)
        scan_content_digests.add(scan_content_digest)
        if scan_file_digest in calibration_sources:
            raise ValueError("evaluated raw scan was also used for score calibration")

        sample_rate_hz = int(capture["sample_rate_hz"])
        cell_samples_value = config.cell_duration_s * sample_rate_hz
        if not math.isclose(
            cell_samples_value, round(cell_samples_value), rel_tol=0.0, abs_tol=1e-9
        ):
            raise ValueError("100-ms activity cell is not integral at a path sample rate")
        scratch_cell_count = math.ceil(
            int(capture["declared_sample_count"]) / round(cell_samples_value)
        )
        inventory = raw_replay._load_raw_inventory(
            dataset=dataset,
            window_rows=rows,
            window_start_sample=0,
            window_cell_samples=round(cell_samples_value),
            window_cell_count=scratch_cell_count,
            calibration=calibration,
            config=config,
        )
        contexts.append(
            _PathContext(
                path_id=path_id,
                dataset=dataset,
                dataset_path=path.resolve(),
                dataset_digest=observed_digest,
                scan_content_digest=scan_content_digest,
                window_rows=rows,
                probe_utc=probe_utc,
                inventory=inventory,
            )
        )
    if session_ids == {""} or len(session_ids) != 1:
        raise ValueError("duration inputs must belong to one nonempty session")
    if manifest_digests == {""} or len(manifest_digests) != 1:
        raise ValueError("duration inputs must bind one recording manifest")
    return tuple(sorted(contexts, key=lambda item: item.path_id))


def _multipath_problem(
    contexts: tuple[_PathContext, ...],
    *,
    start_utc_ns: int,
    end_utc_ns: int,
    config: MultipathReplayConfig,
) -> MultipathSatelliteActivityProblem:
    paths = []
    for context in contexts:
        source_probe_by_id = {item.probe_id: item for item in context.inventory.problem.probes}
        utc_by_id = {item.probe_id: item for item in context.probe_utc}
        probes = tuple(
            CfoProbe(
                probe_id=probe_id,
                time_s=utc_by_id[probe_id].estimate_utc_ns / 1e9,
                cell_index=utc_by_id[probe_id].cell_index,
                missed_detection_cost=source_probe_by_id[probe_id].missed_detection_cost,
                usable=source_probe_by_id[probe_id].usable,
            )
            for probe_id in sorted(
                source_probe_by_id,
                key=lambda item: utc_by_id[item].estimate_utc_ns,
            )
        )
        paths.append(
            ReceiverPathActivityEvidence(
                path_id=context.path_id,
                probes=probes,
                observations=context.inventory.problem.observations,
                truncated_observation_count=0,
            )
        )
    return MultipathSatelliteActivityProblem(
        grid=ActivityGrid(
            start_s=start_utc_ns / 1e9,
            cell_duration_s=config.cell_duration_s,
            cell_count=(end_utc_ns - start_utc_ns) // UTC_CELL_NS,
            minimum_active_cells=config.minimum_active_cells,
            allow_left_censored=False,
            allow_right_censored=False,
        ),
        paths=tuple(paths),
        costs=AssociationCostModel(
            satellite_cost=config.satellite_cost,
            episode_cost=config.episode_cost,
            huber_threshold=config.huber_threshold,
        ),
    )


def _path_doppler(
    *,
    catalogue: Any,
    satellite_index: int,
    context: _PathContext,
    delay_s: float,
    observer: ObserverSiteV1,
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    first_utc_ns = int(context.dataset["timing_binding"]["first_estimate_utc_ns"])
    relative_times_s = tuple(
        (item.estimate_utc_ns - first_utc_ns) / 1e9 for item in context.probe_utc
    )
    return _doppler_curve(
        catalogue=catalogue,
        satellite_index=satellite_index,
        first_sample_utc_ns=first_utc_ns,
        scheduled_times_s=relative_times_s,
        delay_s=delay_s,
        sky_frequency_hz=float(context.dataset["frequency_binding"]["sky_frequency_hz"]),
        observer=observer,
    )


def _state_sort_key(item: _StateEvaluation) -> tuple[object, ...]:
    return (
        item.single_total_cost,
        not item.single_selected,
        abs(item.hypothesis.delay_s),
        tuple(-path.support_probe_count for path in item.paths),
        tuple(abs(path.cfo_offset_hz) for path in item.paths),
        item.hypothesis.hypothesis_id,
    )


def _catalog_state_bank(
    *,
    catalogue: Any,
    catalog_number: int,
    contexts: tuple[_PathContext, ...],
    problem: MultipathSatelliteActivityProblem,
    calibration: Any,
    observer: ObserverSiteV1,
    config: MultipathReplayConfig,
    eligibility_by_path: dict[str, tuple[bool, ...]],
) -> _CatalogBank:
    satellite_index = _unique_satellite_index(catalogue, catalog_number)
    object_name = str(catalogue.names[satellite_index])
    generated = []
    possible_combination_count = 0
    evaluated_combination_count = 0
    exhausted = True
    for delay_s in config.delay_grid:
        fixed_by_path = []
        modes_by_path = []
        for context in contexts:
            eligible_by_cell = eligibility_by_path[context.path_id]
            curve, elevation, _altitude = _path_doppler(
                catalogue=catalogue,
                satellite_index=satellite_index,
                context=context,
                delay_s=delay_s,
                observer=observer,
            )
            minimum_elevation = float(np.min(elevation))
            maximum_elevation = float(np.max(elevation))
            if minimum_elevation <= config.horizon_mask_deg:
                raise ValueError(
                    f"NORAD {catalog_number} falls at or below the full-window horizon gate"
                )
            eligible_probe_ids = {
                item.probe_id for item in context.probe_utc if eligible_by_cell[item.cell_index]
            }
            modes = raw_replay._offset_modes(
                raw=tuple(
                    item
                    for item in context.inventory.observations
                    if item.probe_id in eligible_probe_ids
                ),
                base_prediction_hz=curve,
                calibration=calibration,
                config=config,
            )
            fixed_by_path.append(
                (
                    context,
                    tuple(float(value) for value in curve),
                    minimum_elevation,
                    maximum_elevation,
                    eligible_by_cell,
                )
            )
            modes_by_path.append(modes)
        possible_at_delay = math.prod(len(item) for item in modes_by_path)
        possible_combination_count += possible_at_delay
        mode_products = itertools.islice(
            itertools.product(*modes_by_path),
            config.maximum_path_offset_combinations_per_delay,
        )
        evaluated_at_delay = 0
        for modes in mode_products:
            evaluated_at_delay += 1
            path_states = tuple(
                _PathModeState(
                    path_id=context.path_id,
                    cfo_offset_hz=mode.cfo_offset_hz,
                    support_group_count=mode.support_group_count,
                    support_probe_count=mode.support_probe_count,
                    minimum_elevation_deg=minimum_elevation,
                    maximum_elevation_deg=maximum_elevation,
                    predictions_hz=curve,
                    eligible_by_cell=eligible_by_cell,
                )
                for (
                    context,
                    curve,
                    minimum_elevation,
                    maximum_elevation,
                    eligible_by_cell,
                ), mode in zip(fixed_by_path, modes, strict=True)
            )
            delay_prior_cost = (
                0.5 * ((delay_s - config.delay_prior_mean_s) / config.delay_prior_sigma_s) ** 2
            )
            hypothesis_id = canonical_digest(
                {
                    "catalog_number": catalog_number,
                    "delay_s": delay_s,
                    "path_cfo_offsets_hz": [
                        [item.path_id, item.cfo_offset_hz] for item in path_states
                    ],
                    "eligible_cell_runs_by_path": [
                        [item.path_id, _eligible_cell_runs(item.eligible_by_cell)]
                        for item in path_states
                    ],
                    "prediction_epoch": "persisted_probe_start_utc_estimate",
                }
            )
            hypothesis = FixedMultipathSatelliteHypothesis(
                hypothesis_id=hypothesis_id,
                object_name=object_name,
                catalog_number=catalog_number,
                delay_s=delay_s,
                delay_prior_cost=delay_prior_cost,
                paths=tuple(
                    ReceiverPathFixedHypothesis(
                        path_id=state.path_id,
                        cfo_offset_hz=state.cfo_offset_hz,
                        predictions=tuple(
                            PredictedProbeCfo(probe.probe_id, state.predictions_hz[index])
                            for index, probe in enumerate(
                                next(
                                    item for item in problem.paths if item.path_id == state.path_id
                                ).probes
                            )
                        ),
                        eligible_by_cell=state.eligible_by_cell,
                    )
                    for state in path_states
                ),
            )
            single = decode_fixed_multipath_satellite(problem, hypothesis)
            generated.append(
                _StateEvaluation(
                    hypothesis=hypothesis,
                    paths=path_states,
                    single_total_cost=single.objective.total_cost,
                    single_delta_from_null=single.objective.delta_from_null,
                    single_selected=single.selected,
                )
            )
        evaluated_combination_count += evaluated_at_delay
        if evaluated_at_delay != possible_at_delay:
            exhausted = False
    ordered = tuple(sorted(generated, key=_state_sort_key))
    retained = ordered[: config.retained_states_per_catalog]
    if not retained:
        raise RuntimeError(f"NORAD {catalog_number} generated no multipath nuisance states")
    return _CatalogBank(
        generated=ordered,
        retained=retained,
        possible_path_offset_combination_count=possible_combination_count,
        evaluated_path_offset_combination_count=evaluated_combination_count,
        path_offset_cartesian_exhausted=exhausted,
    )


def _state_document(
    item: _StateEvaluation, *, retained: bool, config: MultipathReplayConfig
) -> dict[str, Any]:
    return {
        "hypothesis_id": item.hypothesis.hypothesis_id,
        "catalog_number": item.hypothesis.catalog_number,
        "object_name": item.hypothesis.object_name,
        "delay_s": item.hypothesis.delay_s,
        "delay_prior_cost": item.hypothesis.delay_prior_cost,
        "delay_at_lower_grid_boundary": math.isclose(
            item.hypothesis.delay_s, config.delay_min_s, rel_tol=0.0, abs_tol=1e-12
        ),
        "delay_at_upper_grid_boundary": math.isclose(
            item.hypothesis.delay_s, config.delay_max_s, rel_tol=0.0, abs_tol=1e-12
        ),
        "paths": [
            {
                "path_id": path.path_id,
                "cfo_offset_hz": path.cfo_offset_hz,
                "mode_support_group_count": path.support_group_count,
                "mode_support_probe_count": path.support_probe_count,
                "cfo_offset_has_data_proposal_support": path.support_probe_count > 0,
                "minimum_elevation_deg": path.minimum_elevation_deg,
                "maximum_elevation_deg": path.maximum_elevation_deg,
                "eligible_cell_runs": _eligible_cell_runs(path.eligible_by_cell),
                "eligible_cell_count": sum(path.eligible_by_cell),
            }
            for path in item.paths
        ],
        "single_satellite_selected": item.single_selected,
        "single_satellite_total_cost": item.single_total_cost,
        "single_satellite_delta_from_null": item.single_delta_from_null,
        "retained_for_joint_search": retained,
    }


def _serialize_inventory(context: _PathContext) -> dict[str, Any]:
    inventory = context.inventory
    return {
        "path_id": context.path_id,
        "duration_input_path": str(context.dataset_path),
        "duration_input_digest": context.dataset_digest,
        "pilot_scan_path": str(inventory.scan_path),
        "pilot_scan_digest": inventory.scan_digest,
        "pilot_scan_content_digest": context.scan_content_digest,
        "sky_frequency_hz": float(context.dataset["frequency_binding"]["sky_frequency_hz"]),
        "scheduled_probe_count": len(context.window_rows),
        "usable_probe_count": sum(item.usable for item in context.probe_utc),
        "usable_empty_probe_count": sum(
            item.usable and item.retained_candidate_count == 0 for item in context.probe_utc
        ),
        "unusable_probe_count": sum(not item.usable for item in context.probe_utc),
        "timing_interval_crosses_cell_boundary_count": sum(
            item.crosses_cell_boundary for item in context.probe_utc
        ),
        "source_candidate_count": inventory.source_candidate_count,
        "returned_candidate_count": inventory.returned_candidate_count,
        "truncated_candidate_count": 0,
        "probe_count_at_retained_candidate_cap": inventory.saturated_probe_count,
        "exclusion_group_count": inventory.exclusion_group_count,
        "positive_exclusion_group_count": inventory.positive_exclusion_group_count,
        "modeled_exclusion_group_count": inventory.modeled_exclusion_group_count,
        "unsupported_positive_exclusion_group_count": (
            inventory.unsupported_positive_exclusion_group_count
        ),
        "dominated_weak_exclusion_group_count": inventory.dominated_weak_exclusion_group_count,
        "constant_elided_from_exact_decision_problem": inventory.elided_clutter_constant,
        "probe_grid_mapping": [
            {
                "probe_id": item.probe_id,
                "estimate_utc_ns": item.estimate_utc_ns,
                "earliest_utc_ns": item.earliest_utc_ns,
                "latest_utc_ns": item.latest_utc_ns,
                "cell_index": item.cell_index,
                "usable_for_activity": item.usable,
                "retained_candidate_count": item.retained_candidate_count,
                "timing_interval_crosses_cell_boundary": item.crosses_cell_boundary,
            }
            for item in context.probe_utc
        ],
    }


def _full_path_objectives(result: Any, contexts: tuple[_PathContext, ...]) -> list[dict[str, Any]]:
    constant_by_path = {item.path_id: item.inventory.elided_clutter_constant for item in contexts}
    documents = []
    for path in result.paths:
        constant = constant_by_path[path.path_id]
        objective = asdict(path.objective)
        documents.append(
            {
                "path_id": path.path_id,
                "null_cost": objective["null_cost"] + constant,
                "total_cost": objective["total_cost"] + constant,
                "delta_from_null": objective["delta_from_null"],
                "constant_elided_from_exact_decision_problem": constant,
                "exact_modeled_group_objective": objective,
            }
        )
    return documents


def _latent_activity_support(satellite: Any, contexts: tuple[_PathContext, ...]) -> dict[str, Any]:
    if not satellite.paths:
        raise ValueError("satellite decision has no receiver paths")
    cell_count = len(satellite.activity_by_cell)
    eligibility_by_path = {item.path_id: item.eligible_by_cell for item in satellite.paths}
    if any(len(mask) != cell_count for mask in eligibility_by_path.values()):
        raise ValueError("satellite path eligibility disagrees with its activity grid")
    usable_cells_by_path = {
        context.path_id: {item.cell_index for item in context.probe_utc if item.usable}
        for context in contexts
    }
    any_rf_eligible = tuple(
        any(mask[cell_index] for mask in eligibility_by_path.values())
        for cell_index in range(cell_count)
    )
    any_eligible_usable_probe = tuple(
        any(
            mask[cell_index] and cell_index in usable_cells_by_path[path_id]
            for path_id, mask in eligibility_by_path.items()
        )
        for cell_index in range(cell_count)
    )
    active = tuple(satellite.activity_by_cell)
    all_paths_ineligible_active = tuple(
        is_active and not is_eligible
        for is_active, is_eligible in zip(active, any_rf_eligible, strict=True)
    )
    no_eligible_usable_probe_active = tuple(
        is_active and not has_probe
        for is_active, has_probe in zip(active, any_eligible_usable_probe, strict=True)
    )
    return {
        "global_activity_is_latent": True,
        "global_active_cell_count": sum(active),
        "global_active_cell_runs": _eligible_cell_runs(active),
        "active_cell_with_any_rf_eligible_path_count": sum(
            is_active and is_eligible
            for is_active, is_eligible in zip(active, any_rf_eligible, strict=True)
        ),
        "all_paths_rf_ineligible_active_cell_count": sum(all_paths_ineligible_active),
        "all_paths_rf_ineligible_active_cell_runs": _eligible_cell_runs(
            all_paths_ineligible_active
        ),
        "no_eligible_usable_probe_active_cell_count": sum(no_eligible_usable_probe_active),
        "no_eligible_usable_probe_active_cell_runs": _eligible_cell_runs(
            no_eligible_usable_probe_active
        ),
    }


def _selected_path_details(
    result: Any,
    banks: dict[int, _CatalogBank],
    contexts: tuple[_PathContext, ...],
) -> dict[str, Any]:
    state_by_id = {
        item.hypothesis.hypothesis_id: item for bank in banks.values() for item in bank.generated
    }
    context_by_path = {item.path_id: item for item in contexts}
    output = {}
    for satellite in result.satellites:
        if not satellite.selected:
            continue
        state = state_by_id[satellite.hypothesis_id]
        state_path_by_id = {item.path_id: item for item in state.paths}
        satellite_paths = {}
        for path in satellite.paths:
            context = context_by_path[path.path_id]
            raw_by_id = {item.observation_id: item for item in context.inventory.observations}
            probe_utc_by_id = {item.probe_id: item for item in context.probe_utc}
            # The inventory probe order matches the persisted UTC/window order.
            geometric_by_probe = {
                probe.probe_id: state_path_by_id[path.path_id].predictions_hz[index]
                for index, probe in enumerate(context.inventory.problem.probes)
            }
            satellite_paths[path.path_id] = {
                "cfo_offset_hz": path.cfo_offset_hz,
                "cfo_offset_has_data_proposal_support": (
                    state_path_by_id[path.path_id].support_probe_count > 0
                ),
                "eligible_by_cell": list(path.eligible_by_cell),
                "eligible_cell_runs": _eligible_cell_runs(path.eligible_by_cell),
                "eligible_cell_count": sum(path.eligible_by_cell),
                "assignments": [
                    {
                        "probe_id": assignment.probe_id,
                        "observation_id": assignment.observation_id,
                        "exclusion_group_id": raw_by_id[
                            assignment.observation_id
                        ].exclusion_group_id,
                        "estimate_utc_ns": probe_utc_by_id[assignment.probe_id].estimate_utc_ns,
                        "observed_cfo_hz": raw_by_id[assignment.observation_id].cfo_hz,
                        "geometric_doppler_hz": geometric_by_probe[assignment.probe_id],
                        "predicted_cfo_hz": (
                            geometric_by_probe[assignment.probe_id] + path.cfo_offset_hz
                        ),
                        "residual_hz": (
                            raw_by_id[assignment.observation_id].cfo_hz
                            - geometric_by_probe[assignment.probe_id]
                            - path.cfo_offset_hz
                        ),
                        "glrt64_margin": raw_by_id[assignment.observation_id].margin,
                        "candidate_rank": raw_by_id[assignment.observation_id].rank,
                        "group_minimum_rank": raw_by_id[
                            assignment.observation_id
                        ].group_minimum_rank,
                        "group_member_count": raw_by_id[
                            assignment.observation_id
                        ].group_member_count,
                    }
                    for assignment in path.assignments
                ],
                "missed_probe_ids": list(path.missed_probe_ids),
                "evidence_objective": asdict(path.evidence),
            }
        output[satellite.hypothesis_id] = {
            "catalog_number": satellite.catalog_number,
            "delay_s": satellite.delay_s,
            "latent_activity_support": _latent_activity_support(satellite, contexts),
            "paths": satellite_paths,
        }
    return output


def replay_raw_multipath_window(
    *,
    dataset_paths: tuple[Path, ...],
    expected_dataset_digests: tuple[str, ...],
    calibration_document: dict[str, Any],
    calibration_path: Path,
    expected_calibration_digest: str,
    tle_path: Path,
    expected_tle_digest: str,
    catalog_numbers: tuple[int, ...],
    start_utc_ns: int,
    end_utc_ns: int,
    observer: ObserverSiteV1,
    config: MultipathReplayConfig,
    eligibility_document: dict[str, Any] | None = None,
    eligibility_plan_path: Path | None = None,
    expected_eligibility_plan_digest: str | None = None,
) -> dict[str, Any]:
    """Build, search, exactly decode fixed states, and serialize one replay."""

    if start_utc_ns < 0 or end_utc_ns <= start_utc_ns:
        raise ValueError("absolute UTC replay window must be nonnegative and increasing")
    if start_utc_ns % UTC_CELL_NS or end_utc_ns % UTC_CELL_NS:
        raise ValueError("absolute UTC window must align to 100-ms Unix-epoch boundaries")
    if not 2 <= len(catalog_numbers) <= 3 or len(set(catalog_numbers)) != len(catalog_numbers):
        raise ValueError("multipath replay requires two or three unique catalogue objects")
    calibration_digest = _file_digest(calibration_path)
    if calibration_digest != _canonical_sha256(
        expected_calibration_digest, "score-calibration digest"
    ):
        raise ValueError("score-calibration file digest mismatch")
    if calibration_document != _read_json(calibration_path):
        raise ValueError("score-calibration document does not match its digest-bound file")
    if calibration_document.get("schema") != raw_replay.CALIBRATION_SCHEMA_V3:
        raise ValueError("multipath replay requires raw V3 resolution-group calibration")
    raw_replay._validate_calibration_grouping(calibration_document, config)
    calibration = raw_replay._score(calibration_document)
    if not calibration.weak_match_is_dominated_by_miss():
        raise ValueError("score calibration does not make weak candidates miss-dominated")
    tle_digest = _file_digest(tle_path)
    if tle_digest != _canonical_sha256(expected_tle_digest, "TLE digest"):
        raise ValueError("multipath replay TLE digest mismatch")
    catalogue = parse_element_sets(tle_path.read_text(encoding="utf-8"))
    ordered_catalog_numbers = tuple(sorted(catalog_numbers))
    for catalog_number in ordered_catalog_numbers:
        _unique_satellite_index(catalogue, catalog_number)

    contexts = _load_path_contexts(
        dataset_paths=dataset_paths,
        expected_dataset_digests=expected_dataset_digests,
        calibration=calibration,
        calibration_document=calibration_document,
        start_utc_ns=start_utc_ns,
        end_utc_ns=end_utc_ns,
        config=config,
    )
    problem = _multipath_problem(
        contexts,
        start_utc_ns=start_utc_ns,
        end_utc_ns=end_utc_ns,
        config=config,
    )
    eligibility = _eligibility_binding(
        document=eligibility_document,
        plan_path=eligibility_plan_path,
        expected_plan_digest=expected_eligibility_plan_digest,
        catalog_numbers=ordered_catalog_numbers,
        path_ids=tuple(item.path_id for item in contexts),
        start_utc_ns=start_utc_ns,
        end_utc_ns=end_utc_ns,
    )
    banks = {
        catalog_number: _catalog_state_bank(
            catalogue=catalogue,
            catalog_number=catalog_number,
            contexts=contexts,
            problem=problem,
            calibration=calibration,
            observer=observer,
            config=config,
            eligibility_by_path=eligibility.by_catalog_path[catalog_number],
        )
        for catalog_number in ordered_catalog_numbers
    }

    possible_joint_combinations = math.prod(len(banks[item].retained) for item in banks)
    joint_evaluations = []
    for states in itertools.islice(
        itertools.product(*(banks[item].retained for item in ordered_catalog_numbers)),
        config.maximum_state_combinations,
    ):
        hypotheses = tuple(item.hypothesis for item in states)
        joint_evaluations.append(
            _JointEvaluation(
                hypotheses=hypotheses,
                result=decode_joint_fixed_multipath_satellites(problem, hypotheses),
            )
        )
    if not joint_evaluations:
        raise RuntimeError("multipath retained state bank generated no joint combinations")
    joint_evaluations.sort(
        key=lambda item: (
            item.result.objective.total_cost,
            len(item.result.selected_catalog_numbers),
            tuple(hypothesis.hypothesis_id for hypothesis in item.hypotheses),
        )
    )
    best = joint_evaluations[0]
    best_hypothesis_ids = tuple(item.hypothesis_id for item in best.hypotheses)
    association = asdict(best.result)
    for satellite_document, satellite in zip(
        association["satellites"], best.result.satellites, strict=True
    ):
        satellite_document["latent_activity_support"] = _latent_activity_support(
            satellite, contexts
        )
    association["selected_catalog_numbers"] = list(best.result.selected_catalog_numbers)
    association["selected_satellite_count"] = len(best.result.selected_catalog_numbers)
    elided_constant = math.fsum(item.inventory.elided_clutter_constant for item in contexts)
    retained_joint_state_space_exhausted = len(joint_evaluations) == possible_joint_combinations
    per_catalog_state_banks_pruned = any(
        len(bank.retained) < len(bank.generated) for bank in banks.values()
    )
    activation_witness = bool(best.result.selected_catalog_numbers)
    full_window_shared_band_occupancy_assumed = all(
        all(mask) for by_path in eligibility.by_catalog_path.values() for mask in by_path.values()
    )

    search_configuration = {
        "algorithm": ALGORITHM,
        "fixed_joint_algorithm": FIXED_JOINT_ALGORITHM,
        "output_schema": OUTPUT_SCHEMA,
        "input_schema": INPUT_SCHEMA,
        "implementation_file_digests": _implementation_file_digests(),
        "runtime_versions": _runtime_versions(),
        "duration_inputs": [
            {
                "path_id": item.path_id,
                "file_digest": item.dataset_digest,
                "pilot_scan_digest": item.inventory.scan_digest,
                "pilot_scan_content_digest": item.scan_content_digest,
                "sky_frequency_hz": float(item.dataset["frequency_binding"]["sky_frequency_hz"]),
            }
            for item in contexts
        ],
        "score_calibration_schema": calibration_document["schema"],
        "score_calibration_digest": calibration_digest,
        "tle_digest": tle_digest,
        "catalog_numbers": list(ordered_catalog_numbers),
        "rf_eligibility": eligibility.receipt,
        "window": {
            "start_utc_ns": start_utc_ns,
            "end_utc_ns": end_utc_ns,
            "cell_duration_ns": UTC_CELL_NS,
        },
        "observer": observer.model_dump(mode="json"),
        "configuration": asdict(config),
    }
    if activation_witness:
        result_kind = "bounded_multipath_catalogue_activity"
    elif retained_joint_state_space_exhausted:
        result_kind = "conditional_null_over_retained_state_bank"
    else:
        result_kind = "conditional_null_over_evaluated_retained_state_prefix"
    return {
        "schema": OUTPUT_SCHEMA,
        "algorithm": ALGORITHM,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
        "catalogue_search_performed": False,
        "catalogue_search_exact": False,
        "global_optimum_claimed": False,
        "conditional_on_explicit_catalog_shortlist": True,
        "conditional_on_raw_glrt64_inventory": True,
        "conditional_on_data_proposed_path_cfo_offsets": True,
        "conditional_on_retained_nuisance_state_bank": True,
        "conditional_on_fixed_path_cell_rf_eligibility": True,
        "external_rf_eligibility_plan_supplied": eligibility.supplied,
        "rf_eligibility_inferred_from_scored_observations": False,
        "rf_eligibility_preregistration_verified": False,
        "full_window_shared_band_occupancy_assumed": (full_window_shared_band_occupancy_assumed),
        "unknown_satellite_count_solved": False,
        "null_vs_any_activation_solved": activation_witness,
        "null_vs_supplied_retained_state_bank_solved": (retained_joint_state_space_exhausted),
        "evaluated_fixed_state_decisions_exact": True,
        "per_catalog_state_banks_pruned": per_catalog_state_banks_pruned,
        "costs_calibrated": False,
        "detector_score_costs_empirically_calibrated": False,
        "score_costs_use_conservative_v3_rank_mark_bounds": True,
        "structural_costs_calibrated": False,
        "search_configuration": search_configuration,
        "search_configuration_digest": canonical_digest(search_configuration),
        "input": {
            "session_id": contexts[0].dataset["capture"]["session_id"],
            "recording_manifest_digest": contexts[0].dataset["capture"][
                "recording_manifest_digest"
            ],
            "duration_inputs": [
                {
                    "path_id": item.path_id,
                    "path": str(item.dataset_path),
                    "file_digest": item.dataset_digest,
                }
                for item in contexts
            ],
            "score_calibration_path": str(calibration_path.resolve()),
            "score_calibration_digest": calibration_digest,
            "tle_path": str(tle_path.resolve()),
            "tle_digest": tle_digest,
            "eligibility_plan": (
                None
                if not eligibility.supplied
                else {
                    "path": str(eligibility.plan_path),
                    "file_digest": eligibility.plan_file_digest,
                    "content_digest": eligibility.receipt["plan_content_digest"],
                }
            ),
        },
        "window": {
            "start_utc_ns": start_utc_ns,
            "end_utc_ns": end_utc_ns,
            "cell_duration_s": config.cell_duration_s,
            "cell_count": problem.grid.cell_count,
            "minimum_active_duration_s": config.minimum_active_duration_s,
            "minimum_active_cells": config.minimum_active_cells,
            "probe_epoch": "persisted_probe_start_utc_estimate",
        },
        "observer": {**observer.model_dump(mode="json"), "capture_bound": False},
        "configuration": asdict(config),
        "score_calibration": asdict(calibration),
        "path_inventories": [_serialize_inventory(item) for item in contexts],
        "nuisance_state_search": {
            "catalogs": [
                {
                    "catalog_number": catalog_number,
                    "generated_state_count": len(banks[catalog_number].generated),
                    "retained_state_count": len(banks[catalog_number].retained),
                    "possible_path_offset_combination_count": banks[
                        catalog_number
                    ].possible_path_offset_combination_count,
                    "evaluated_path_offset_combination_count": banks[
                        catalog_number
                    ].evaluated_path_offset_combination_count,
                    "path_offset_cartesian_exhausted": banks[
                        catalog_number
                    ].path_offset_cartesian_exhausted,
                    "delay_grid_exhausted": True,
                    "generated_state_space_exhausted": banks[
                        catalog_number
                    ].path_offset_cartesian_exhausted,
                    "retained_every_generated_state": (
                        len(banks[catalog_number].retained) == len(banks[catalog_number].generated)
                    ),
                    "states": [
                        _state_document(
                            item,
                            retained=item in banks[catalog_number].retained,
                            config=config,
                        )
                        for item in banks[catalog_number].generated
                    ],
                }
                for catalog_number in ordered_catalog_numbers
            ],
            "possible_retained_joint_state_combination_count": possible_joint_combinations,
            "evaluated_retained_joint_state_combination_count": len(joint_evaluations),
            "retained_joint_state_space_exhausted": retained_joint_state_space_exhausted,
            "every_evaluated_fixed_joint_decision_exact": True,
            "per_catalog_state_banks_pruned": per_catalog_state_banks_pruned,
            "evaluations": [
                {
                    "hypothesis_ids": [hypothesis.hypothesis_id for hypothesis in item.hypotheses],
                    "selected_catalog_numbers": list(item.result.selected_catalog_numbers),
                    "total_cost": item.result.objective.total_cost,
                    "delta_from_null": item.result.objective.delta_from_null,
                    "selected": tuple(hypothesis.hypothesis_id for hypothesis in item.hypotheses)
                    == best_hypothesis_ids,
                }
                for item in joint_evaluations
            ],
        },
        "decision": {
            "result_kind": result_kind,
            "selected_catalog_numbers": list(best.result.selected_catalog_numbers),
            "selected_satellite_count": len(best.result.selected_catalog_numbers),
            "fixed_hypothesis_ids": list(best_hypothesis_ids),
            "null_vs_any_activation_solved": activation_witness,
            "null_vs_supplied_retained_state_bank_solved": (retained_joint_state_space_exhausted),
            "per_catalog_state_banks_pruned": per_catalog_state_banks_pruned,
            "full_persisted_inventory_objective": {
                "null_cost": best.result.objective.null_cost + elided_constant,
                "total_cost": best.result.objective.total_cost + elided_constant,
                "delta_from_null": best.result.objective.delta_from_null,
                "constant_elided_from_exact_decision_problem": elided_constant,
            },
        },
        "association": association,
        "path_full_persisted_inventory_objectives": _full_path_objectives(best.result, contexts),
        "selected_path_assignment_details": _selected_path_details(best.result, banks, contexts),
        "caveats": [
            (
                "the two- or three-object catalogue shortlist is explicit; no catalogue "
                "search was performed"
            ),
            (
                "constant CFO offsets are proposed from the evaluated data before bounded "
                "state pruning"
            ),
            "the delay grid changes orbital evaluation time but does not update an orbit",
            (
                "RF eligibility is fixed independently for every catalogue/path/cell by the "
                + (
                    "digest-bound external plan; the adapter does not verify that the plan was "
                    "preregistered or selected independently of these observations"
                    if eligibility.supplied
                    else "adapter's all-cells-eligible default"
                )
            ),
            (
                "the 0.5-second constraint applies to each satellite's global activity mask; "
                "eligible support on one RF path can be shorter or discontinuous"
            ),
            (
                "episode duration describes latent global persistence, not observed airtime; "
                "active cells with no RF-eligible path or no eligible usable probe are disclosed "
                "as model-imputed bridge cells"
            ),
            (
                "a path CFO offset with zero eligible proposal support is fixed to the canonical "
                "0-Hz mode and is not identified by that path"
            ),
            (
                "the result is exact only for each fixed state and conditional on the bounded "
                "retained nuisance-state bank"
            ),
            (
                "every evaluated retained joint combination is decoded exactly, while each "
                "catalogue bank can still prune data-proposed nuisance states"
            ),
            (
                "when the retained joint Cartesian is capped, an empty decision certifies "
                "only the evaluated deterministic prefix, not the whole retained bank"
            ),
            "nuisance states attached to unselected catalogue objects have no inferential meaning",
            (
                "a selected episode touching a replay-window boundary does not establish its "
                "physical onset or termination"
            ),
            (
                "short-window delay can remain weakly identified after independent path CFO "
                "offsets; the full delay profile and grid boundaries must be inspected"
            ),
            (
                "raw V3 resolution-group score costs are conservative pseudo-likelihood "
                "terms; structural costs remain provisional"
            ),
            (
                "persisted probe UTC estimates select cells; earliest/latest intervals can "
                "cross a cell boundary and are disclosed per path"
            ),
            (
                "post-acquisition candidate inventories declare no truncation, but acquisition "
                "caps can still saturate"
            ),
            "duration-input frame-track evidence is not consumed by this raw-probe replay",
            "observer coordinates are explicit but not capture-bound authority",
            "candidate activity is not payload decoding or spacecraft identity",
        ],
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--input-sha256", action="append", required=True)
    parser.add_argument("--score-calibration", type=Path, required=True)
    parser.add_argument("--score-calibration-sha256", required=True)
    parser.add_argument("--tle", type=Path, required=True)
    parser.add_argument("--tle-sha256", required=True)
    parser.add_argument("--eligibility-plan", type=Path)
    parser.add_argument("--eligibility-plan-sha256")
    parser.add_argument("--catalog-number", action="append", type=int, required=True)
    parser.add_argument("--window-start-utc-ns", type=int, required=True)
    parser.add_argument("--window-end-utc-ns", type=int, required=True)
    parser.add_argument("--observer-latitude-deg", type=float, required=True)
    parser.add_argument("--observer-longitude-deg", type=float, required=True)
    parser.add_argument("--observer-altitude-m", type=float, required=True)
    parser.add_argument("--observer-label", required=True)
    parser.add_argument("--minimum-active-duration-s", type=float, default=0.5)
    parser.add_argument("--cfo-sigma-hz", type=float, default=100.0)
    parser.add_argument("--satellite-cost", type=float, default=5.25)
    parser.add_argument("--episode-cost", type=float, default=5.75)
    parser.add_argument("--huber-threshold", type=float, default=1.345)
    parser.add_argument("--delay-min-s", type=float, default=-2.0)
    parser.add_argument("--delay-max-s", type=float, default=2.0)
    parser.add_argument("--delay-step-s", type=float, default=0.1)
    parser.add_argument("--delay-prior-mean-s", type=float, default=0.0)
    parser.add_argument("--delay-prior-sigma-s", type=float, default=0.5)
    parser.add_argument("--duplicate-cfo-tolerance-hz", type=float, default=0.0)
    parser.add_argument("--resolution-epoch-tolerance-samples", type=int, default=1)
    parser.add_argument("--resolution-tracking-cfo-tolerance-hz", type=float, default=500.0)
    parser.add_argument("--mode-bin-hz", type=float, default=100.0)
    parser.add_argument("--mode-half-width-hz", type=float, default=300.0)
    parser.add_argument("--modes-per-delay", type=int, default=2)
    parser.add_argument("--retained-states-per-catalog", type=int, default=4)
    parser.add_argument("--maximum-state-combinations", type=int, default=256)
    parser.add_argument("--maximum-path-offset-combinations-per-delay", type=int, default=64)
    parser.add_argument("--horizon-mask-deg", type=float, default=0.0)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if (arguments.eligibility_plan is None) != (arguments.eligibility_plan_sha256 is None):
        parser.error("--eligibility-plan and --eligibility-plan-sha256 must be supplied together")
    return arguments


def main() -> int:
    arguments = _arguments()
    config = MultipathReplayConfig(
        minimum_active_duration_s=arguments.minimum_active_duration_s,
        cfo_sigma_hz=arguments.cfo_sigma_hz,
        satellite_cost=arguments.satellite_cost,
        episode_cost=arguments.episode_cost,
        huber_threshold=arguments.huber_threshold,
        delay_min_s=arguments.delay_min_s,
        delay_max_s=arguments.delay_max_s,
        delay_step_s=arguments.delay_step_s,
        delay_prior_mean_s=arguments.delay_prior_mean_s,
        delay_prior_sigma_s=arguments.delay_prior_sigma_s,
        duplicate_cfo_tolerance_hz=arguments.duplicate_cfo_tolerance_hz,
        resolution_epoch_tolerance_samples=arguments.resolution_epoch_tolerance_samples,
        resolution_tracking_cfo_tolerance_hz=(arguments.resolution_tracking_cfo_tolerance_hz),
        mode_bin_hz=arguments.mode_bin_hz,
        mode_half_width_hz=arguments.mode_half_width_hz,
        modes_per_delay=arguments.modes_per_delay,
        retained_states_per_catalog=arguments.retained_states_per_catalog,
        maximum_state_combinations=arguments.maximum_state_combinations,
        maximum_path_offset_combinations_per_delay=(
            arguments.maximum_path_offset_combinations_per_delay
        ),
        horizon_mask_deg=arguments.horizon_mask_deg,
    )
    document = replay_raw_multipath_window(
        dataset_paths=tuple(arguments.input),
        expected_dataset_digests=tuple(arguments.input_sha256),
        calibration_document=_read_json(arguments.score_calibration),
        calibration_path=arguments.score_calibration,
        expected_calibration_digest=arguments.score_calibration_sha256,
        tle_path=arguments.tle,
        expected_tle_digest=arguments.tle_sha256,
        catalog_numbers=tuple(arguments.catalog_number),
        start_utc_ns=arguments.window_start_utc_ns,
        end_utc_ns=arguments.window_end_utc_ns,
        observer=ObserverSiteV1(
            latitude_deg=arguments.observer_latitude_deg,
            longitude_deg=arguments.observer_longitude_deg,
            altitude_m=arguments.observer_altitude_m,
            label=arguments.observer_label,
        ),
        config=config,
        eligibility_document=(
            None if arguments.eligibility_plan is None else _read_json(arguments.eligibility_plan)
        ),
        eligibility_plan_path=arguments.eligibility_plan,
        expected_eligibility_plan_digest=arguments.eligibility_plan_sha256,
    )
    rendered = json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        _refuse_qnap_output(arguments.output)
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
