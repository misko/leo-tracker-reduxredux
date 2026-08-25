#!/usr/bin/env python3
"""Replay research PNT-Kalman V4 on the frozen 2026-08-25 canary.

This tool is deliberately narrower than a general recording replay.  It binds
the 537 trajectory-conditioned rows, recording manifest, and compressed IQ
chunks used by the published V3 full-dwell comparison.  V4 remains a research
canary: numerical acquisition, tracking, and phase qualification are reported
separately and this tool does not write Standard products.

Row checkpoints are deterministic and independently reusable.  An interrupted
run can be resumed without re-reading IQ for completed rows.  Every serialized
V4 proposal must either have a candidate record or be counted explicitly as a
truncated proposal before a checkpoint is accepted.
"""

from __future__ import annotations

import argparse
import dataclasses
import enum
import hashlib
import inspect
import json
import math
import os
import tempfile
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import zstandard as zstd

SCHEMA = "org.leo.research.pnt-kalman-v4-150802-canary/v1"
ROW_SCHEMA = "org.leo.research.pnt-kalman-v4-150802-canary-row/v1"
INDEX_SCHEMA = "org.leo.research.pnt-kalman-v4-150802-canary-index/v1"

SESSION_ID = "cap-20260825T150802-473cb5bbcbd6"
RUN_ID = "capture-a5d45dd7752c4fc7833cd017a289f8d7"
FROZEN_ROW_COUNT = 537
FROZEN_INPUT_SHA256 = "sha256:6b740a994181f13e9c6e21538026ee7531d68edbb9c40c54bab26ee11fe1b9a4"
FROZEN_RECORDING_MANIFEST_SHA256 = (
    "sha256:ab55917851a9cd37af94b6145cc719f7b8d9d0809f2202a2dcd1ac38c3e7a31e"
)
DEFAULT_INPUT = Path("reports/figures/2026_08_25_150802_v3_full_dwell/full-dwell-results.json")
DEFAULT_CAPTURE_ROOT = Path("/srv/bulk/leo/recordings/2026/08/25/cap-20260825T150802-473cb5bbcbd6")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
QNAP_ROOT = Path("/mnt/qnap01")
SAMPLE_RATE_HZ = 2_500_000.0
WINDOW_DURATION_S = 0.075
WINDOW_SAMPLE_COUNT = round(SAMPLE_RATE_HZ * WINDOW_DURATION_S)
OFDM_CFO_ALIAS_HZ = 1.0 / 4.4e-6

PUBLISHED_GATES: dict[str, Any] = {
    "population_row_count": FROZEN_ROW_COUNT,
    "standard_qualified_control_count": 53,
    "v2_phase_qualified_control_count": 55,
    "robust_v3_loss_count": 50,
    "one_update_alias_count": 7,
    "matched_alias_null_peer_count": 57,
    "requirements": {
        "standard_qualified_controls_tracked": 53,
        "v2_phase_qualified_controls_tracked": 55,
        "robust_v3_losses_selected": 50,
        "robust_v3_losses_tracked": 50,
        "one_update_alias_independent_tracks": 0,
        "matched_alias_null_peers_selected": 0,
        "matched_alias_null_peers_tracked": 0,
        "all_rows_and_proposals_accounted": True,
        "phase_thresholds_unchanged": True,
        "research_claim_boundaries_preserved": True,
    },
    "qualification_policy": (
        "Acquisition recovery and numerical tracking are not scientific qualification. "
        "New phase-qualified rows are review items, never automatic promotions."
    ),
}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--capture-root", type=Path, default=DEFAULT_CAPTURE_ROOT)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--maximum-rows",
        type=int,
        help="bounded development run; omitted means the complete frozen population",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="checkpoint execution errors and continue so failures remain accounted",
    )
    return parser.parse_args()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _value_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _plain(value: Any) -> Any:
    """Convert dataclasses/enums/NumPy scalars to deterministic JSON values."""

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _plain(dataclasses.asdict(value))
    if isinstance(value, enum.Enum):
        return _plain(value.value)
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, np.generic):
        return _plain(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("V4 evidence contains a nonfinite float")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"V4 evidence contains a non-JSON value: {type(value).__name__}")


def _alias_class_ids(
    modes: Sequence[Any],
    *,
    cfo_tolerance_hz: float,
    rate_tolerance_hz_s: float,
    timing_tolerance_samples: float,
) -> dict[int, str]:
    """Group one compatible trajectory modulo one constant CFO-alias quotient.

    Source provenance and alias lift are deliberately absent from the
    equivalence test.  They describe how a proposal arrived, not a distinct
    physical mode.  A shared reference epoch is not sufficient: the complete
    timing path and Doppler rate must also agree, and every block CFO must
    differ by the same integer OFDM-symbol alias quotient.
    """

    tolerances = (cfo_tolerance_hz, rate_tolerance_hz_s, timing_tolerance_samples)
    if not all(math.isfinite(value) for value in tolerances):
        raise ValueError("alias-class tolerances must be finite")
    if cfo_tolerance_hz <= 0.0 or rate_tolerance_hz_s < 0.0 or timing_tolerance_samples < 0.0:
        raise ValueError("alias-class tolerances are outside their valid range")

    def field(mode: Any, name: str) -> Any:
        return mode[name] if isinstance(mode, Mapping) else getattr(mode, name)

    def equivalent(left: Any, right: Any) -> bool:
        left_epoch_residuals = tuple(
            float(value) for value in field(left, "trajectory_block_epoch_residual_samples")
        )
        right_epoch_residuals = tuple(
            float(value) for value in field(right, "trajectory_block_epoch_residual_samples")
        )
        left_cfos_hz = tuple(
            float(value) for value in field(left, "trajectory_block_absolute_cfo_hz")
        )
        right_cfos_hz = tuple(
            float(value) for value in field(right, "trajectory_block_absolute_cfo_hz")
        )
        if (
            int(field(left, "epoch_sample")) != int(field(right, "epoch_sample"))
            or not left_epoch_residuals
            or len(left_epoch_residuals) != len(right_epoch_residuals)
            or len(left_cfos_hz) != len(right_cfos_hz)
            or len(left_cfos_hz) != len(left_epoch_residuals)
            or abs(
                float(field(left, "doppler_rate_hz_s")) - float(field(right, "doppler_rate_hz_s"))
            )
            > rate_tolerance_hz_s
        ):
            return False
        if any(
            abs(left_value - right_value) > timing_tolerance_samples
            for left_value, right_value in zip(
                left_epoch_residuals,
                right_epoch_residuals,
                strict=True,
            )
        ):
            return False
        quotients = []
        for left_cfo_hz, right_cfo_hz in zip(left_cfos_hz, right_cfos_hz, strict=True):
            difference_hz = left_cfo_hz - right_cfo_hz
            quotient = round(difference_hz / OFDM_CFO_ALIAS_HZ)
            residual_hz = difference_hz - quotient * OFDM_CFO_ALIAS_HZ
            if abs(residual_hz) > cfo_tolerance_hz:
                return False
            quotients.append(quotient)
        return bool(quotients) and len(set(quotients)) == 1

    representatives: list[Any] = []
    identifiers: list[str] = []
    output: dict[int, str] = {}
    for mode in modes:
        identifier = None
        for representative, candidate in zip(representatives, identifiers, strict=True):
            if equivalent(mode, representative):
                identifier = candidate
                break
        if identifier is None:
            reference_alias_quotient = round(
                (float(field(mode, "absolute_cfo_hz")) - float(field(mode, "canonical_cfo_hz")))
                / OFDM_CFO_ALIAS_HZ
            )
            identifier = _value_digest(
                {
                    "epoch_sample": int(field(mode, "epoch_sample")),
                    "canonical_cfo_hz": float(field(mode, "canonical_cfo_hz")),
                    "doppler_rate_hz_s": float(field(mode, "doppler_rate_hz_s")),
                    "trajectory_block_epoch_residual_samples": [
                        int(value)
                        for value in field(mode, "trajectory_block_epoch_residual_samples")
                    ],
                    "trajectory_block_canonical_cfo_hz": [
                        float(value) - reference_alias_quotient * OFDM_CFO_ALIAS_HZ
                        for value in field(mode, "trajectory_block_absolute_cfo_hz")
                    ],
                }
            )
            representatives.append(mode)
            identifiers.append(identifier)
        output[id(mode)] = identifier
    return output


def _candidate_id(mode: Any) -> str:
    """Content-address one retained proposal, including its selected path."""

    def field(name: str) -> Any:
        return mode[name] if isinstance(mode, Mapping) else getattr(mode, name)

    return _value_digest(
        {
            "rank": int(field("rank")),
            "proposal_origin": _plain(field("proposal_origin")),
            "proposal_epoch_sample": int(field("proposal_epoch_sample")),
            "proposal_absolute_cfo_hz": float(field("proposal_absolute_cfo_hz")),
            "epoch_sample": int(field("epoch_sample")),
            "absolute_cfo_hz": float(field("absolute_cfo_hz")),
            "doppler_rate_hz_s": float(field("doppler_rate_hz_s")),
            "canonical_cfo_hz": float(field("canonical_cfo_hz")),
            "cfo_alias_lift": int(field("cfo_alias_lift")),
            "trajectory_path_sha256": str(field("trajectory_path_sha256")),
            "source_seed_index": int(field("source_seed_index")),
            "source_branch_id": str(field("source_branch_id")),
            "source_provenance_sha256": str(field("source_provenance_sha256")),
        }
    )


@dataclass(frozen=True, slots=True)
class FrozenRow:
    index: int
    row_key: str
    row_input_digest: str
    source: dict[str, Any]

    @property
    def sample_start(self) -> int:
        return int(self.source["source_probe_sample_start"])


@dataclass(frozen=True, slots=True)
class FrozenInput:
    path: Path
    digest: str
    document: dict[str, Any]
    rows: tuple[FrozenRow, ...]


def _row_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "scope": row["scope"],
        "source_trajectory_id": row["source_trajectory_id"],
        "source_probe_sample_start": int(row["source_probe_sample_start"]),
        "segment_index": int(row["segment_index"]),
        "candidate_rank": int(row["candidate_rank"]),
        "stream": row["stream"],
        "receiver": int(row["receiver"]),
    }


def frozen_rows(document: Mapping[str, Any]) -> tuple[FrozenRow, ...]:
    source_rows = document.get("windows")
    if not isinstance(source_rows, list):
        raise ValueError("frozen input windows must be a list")
    rows = []
    for index, source in enumerate(source_rows):
        if not isinstance(source, dict):
            raise ValueError(f"frozen input row {index} is not an object")
        identity = _row_identity(source)
        rows.append(
            FrozenRow(
                index=index,
                row_key=_value_digest(identity),
                row_input_digest=_value_digest(source),
                source=dict(source),
            )
        )
    keys = {row.row_key for row in rows}
    if len(keys) != len(rows):
        raise ValueError("frozen input row identities are not unique")
    return tuple(rows)


def load_frozen_input(path: Path, *, enforce_binding: bool = True) -> FrozenInput:
    digest = _file_digest(path)
    if enforce_binding and digest != FROZEN_INPUT_SHA256:
        raise ValueError(
            f"frozen V3 input digest changed: expected {FROZEN_INPUT_SHA256}, got {digest}"
        )
    document = _json_object(path)
    if document.get("schema_version") != 1:
        raise ValueError("unexpected frozen V3 input schema")
    if document.get("session_id") != SESSION_ID or document.get("run_id") != RUN_ID:
        raise ValueError("frozen V3 capture identity changed")
    rows = frozen_rows(document)
    expected = FROZEN_ROW_COUNT if enforce_binding else len(rows)
    if len(rows) != expected:
        raise ValueError(f"expected {expected} frozen rows, found {len(rows)}")
    aggregate = document.get("aggregate")
    if not isinstance(aggregate, dict) or aggregate.get("source_window_count") != len(rows):
        raise ValueError("frozen V3 aggregate does not account every source row")
    if enforce_binding:
        replay = document.get("replay")
        if not isinstance(replay, dict) or replay.get("sample_rate_hz") != SAMPLE_RATE_HZ:
            raise ValueError("frozen V3 replay sample rate changed")
    return FrozenInput(path=path, digest=digest, document=document, rows=rows)


def published_cohorts(rows: Sequence[FrozenRow]) -> dict[str, tuple[str, ...]]:
    """Return the deterministic row cohorts named by the published V4 gates."""

    robust = tuple(
        row.row_key
        for row in rows
        if row.source["v2_status"] == "complete"
        and row.source["v3_status"] == "no_result"
        and int(row.source["v2_frequency_update_count"]) > 1
    )
    one_update = tuple(
        row.row_key
        for row in rows
        if row.source["v2_status"] == "complete"
        and row.source["v3_status"] == "no_result"
        and int(row.source["v2_frequency_update_count"]) == 1
    )
    standard = tuple(row.row_key for row in rows if row.source["standard_v1_qualified"])
    v2_phase = tuple(row.row_key for row in rows if row.source["v2_phase_lock_qualified"])

    null_pool = {
        row.row_key: row
        for row in rows
        if row.source["v2_status"] == "no_result" and row.source["v3_status"] == "no_result"
    }
    by_key = {row.row_key: row for row in rows}
    matched_null = []
    for target_key in sorted(
        robust + one_update,
        key=lambda key: (
            str(by_key[key].source["scope"]),
            float(by_key[key].source["start_time_s"]),
            key,
        ),
    ):
        target = by_key[target_key]
        choices = [
            row for row in null_pool.values() if row.source["scope"] == target.source["scope"]
        ]
        if not choices:
            raise ValueError(f"no same-scope alias/null peer for {target_key}")
        selected = min(
            choices,
            key=lambda row: (
                abs(float(row.source["start_time_s"]) - float(target.source["start_time_s"])),
                abs(
                    (float(row.source["seed_cfo_hz"]) - float(target.source["seed_cfo_hz"]))
                    / OFDM_CFO_ALIAS_HZ
                    - round(
                        (float(row.source["seed_cfo_hz"]) - float(target.source["seed_cfo_hz"]))
                        / OFDM_CFO_ALIAS_HZ
                    )
                ),
                row.row_key,
            ),
        )
        matched_null.append(selected.row_key)
        del null_pool[selected.row_key]

    cohorts = {
        "standard_qualified_controls": tuple(sorted(standard)),
        "v2_phase_qualified_controls": tuple(sorted(v2_phase)),
        "robust_v3_losses": tuple(sorted(robust)),
        "one_update_aliases": tuple(sorted(one_update)),
        "matched_alias_null_peers": tuple(sorted(matched_null)),
    }
    expected_counts = {
        "standard_qualified_controls": 53,
        "v2_phase_qualified_controls": 55,
        "robust_v3_losses": 50,
        "one_update_aliases": 7,
        "matched_alias_null_peers": 57,
    }
    if len(rows) == FROZEN_ROW_COUNT:
        actual = {name: len(keys) for name, keys in cohorts.items()}
        if actual != expected_counts:
            raise ValueError(f"published cohort accounting changed: {actual}")
    return cohorts


@dataclass(frozen=True, slots=True)
class ChunkReceipt:
    relative_path: str
    compressed_sha256: str
    uncompressed_sha256: str
    sample_start: int
    sample_count: int


class FrozenCi16Reader:
    """Minimal read-only manifest-V2 ci16 reader with bounded verified cache."""

    def __init__(
        self,
        capture_root: Path,
        *,
        expected_manifest_digest: str,
        expected_session_id: str,
        maximum_cached_chunks: int = 2,
    ) -> None:
        if maximum_cached_chunks < 1:
            raise ValueError("maximum cached chunks must be positive")
        self.capture_root = capture_root.resolve()
        manifest_path = self.capture_root / "manifest.json"
        actual_digest = _file_digest(manifest_path)
        if actual_digest != expected_manifest_digest:
            raise ValueError(
                f"recording manifest digest changed: expected {expected_manifest_digest}, "
                f"got {actual_digest}"
            )
        self.manifest_digest = actual_digest
        manifest = _json_object(manifest_path)
        if manifest.get("schema_version") != 2:
            raise ValueError("frozen canary requires recording manifest V2")
        if manifest.get("session_id") != expected_session_id:
            raise ValueError("recording manifest session changed")
        streams = manifest.get("streams")
        if not isinstance(streams, list):
            raise ValueError("recording manifest streams must be a list")
        self._streams = {str(stream["stream_id"]): stream for stream in streams}
        if len(self._streams) != len(streams):
            raise ValueError("recording stream IDs are not unique")
        self._maximum_cached_chunks = maximum_cached_chunks
        self._cache: OrderedDict[tuple[str, int], tuple[bytes, np.ndarray]] = OrderedDict()
        self.verified_chunks: dict[str, ChunkReceipt] = {}
        self.sample_rate_hz = float(
            next(iter(self._streams.values()))["applied_settings"]["sample_rate_hz"]
        )

    def _chunk(self, stream_id: str, chunk: Mapping[str, Any]) -> np.ndarray:
        key = (stream_id, int(chunk["chunk_index"]))
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key][1]
        if chunk.get("sample_format") != "ci16_le" or chunk.get("sample_layout") != (
            "sample_receiver_iq"
        ):
            raise ValueError("frozen chunk has an unsupported sample format/layout")
        relative = Path(str(chunk["relative_path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("recording chunk path escapes the capture root")
        path = (self.capture_root / relative).resolve()
        if self.capture_root not in path.parents:
            raise ValueError("recording chunk path escapes the capture root")
        compressed = path.read_bytes()
        compressed_digest = "sha256:" + hashlib.sha256(compressed).hexdigest()
        if compressed_digest != chunk["compressed_sha256"]:
            raise ValueError(f"compressed chunk digest changed: {relative}")
        raw = zstd.ZstdDecompressor().decompress(
            compressed,
            max_output_size=int(chunk["uncompressed_bytes"]),
        )
        if len(raw) != int(chunk["uncompressed_bytes"]):
            raise ValueError(f"uncompressed chunk size changed: {relative}")
        uncompressed_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        if uncompressed_digest != chunk["uncompressed_sha256"]:
            raise ValueError(f"uncompressed chunk digest changed: {relative}")
        receiver_ids = tuple(
            int(value) for value in self._streams[stream_id]["applied_settings"]["receiver_ids"]
        )
        values = np.frombuffer(raw, dtype="<i2").reshape(
            int(chunk["sample_count"]), len(receiver_ids), 2
        )
        self._cache[key] = (raw, values)
        self._cache.move_to_end(key)
        while len(self._cache) > self._maximum_cached_chunks:
            self._cache.popitem(last=False)
        receipt = ChunkReceipt(
            relative_path=str(relative),
            compressed_sha256=compressed_digest,
            uncompressed_sha256=uncompressed_digest,
            sample_start=int(chunk["sample_start"]),
            sample_count=int(chunk["sample_count"]),
        )
        self.verified_chunks[str(relative)] = receipt
        return values

    def read_complex(
        self,
        stream_id: str,
        receiver_id: int,
        sample_start: int,
        sample_count: int,
    ) -> tuple[np.ndarray, tuple[ChunkReceipt, ...]]:
        if sample_start < 0 or sample_count < 1:
            raise ValueError("IQ slice start/count are invalid")
        try:
            stream = self._streams[stream_id]
        except KeyError as error:
            raise ValueError(f"recording stream is absent: {stream_id}") from error
        receiver_ids = tuple(int(value) for value in stream["applied_settings"]["receiver_ids"])
        if receiver_id not in receiver_ids:
            raise ValueError(f"receiver {receiver_id} is absent from {stream_id}")
        receiver_column = receiver_ids.index(receiver_id)
        sample_stop = sample_start + sample_count
        pieces = []
        receipts = []
        for chunk in sorted(stream["chunks"], key=lambda value: int(value["sample_start"])):
            chunk_start = int(chunk["sample_start"])
            chunk_stop = chunk_start + int(chunk["sample_count"])
            overlap_start = max(sample_start, chunk_start)
            overlap_stop = min(sample_stop, chunk_stop)
            if overlap_stop <= overlap_start:
                continue
            values = self._chunk(stream_id, chunk)
            selected = values[
                overlap_start - chunk_start : overlap_stop - chunk_start,
                receiver_column,
            ]
            pieces.append(selected[:, 0].astype(np.float64) + 1j * selected[:, 1])
            receipts.append(self.verified_chunks[str(chunk["relative_path"])])
        if not pieces or sum(len(piece) for piece in pieces) != sample_count:
            raise ValueError("recording chunks do not completely cover the requested IQ slice")
        return np.concatenate(pieces), tuple(receipts)


@dataclass(frozen=True, slots=True)
class AnalyzerBinding:
    api_name: str
    source_sha256: str
    config_digest: str
    config: dict[str, Any]
    analyze: Callable[[np.ndarray, float, FrozenRow], Mapping[str, Any]]
    source_inventory: dict[str, str] = dataclasses.field(default_factory=dict)
    runtime_inventory: dict[str, Any] = dataclasses.field(default_factory=dict)


def _source_inventory(callables: Sequence[Callable[..., Any]]) -> dict[str, str]:
    inventory = {}
    for callable_value in callables:
        path = Path(inspect.getsourcefile(callable_value) or "").resolve()
        if not path.is_file():
            raise RuntimeError("cannot bind V4 analyzer source inventory")
        try:
            name = str(path.relative_to(REPOSITORY_ROOT))
        except ValueError:
            name = path.name
        inventory[name] = _file_digest(path)
    return dict(sorted(inventory.items()))


def load_v4_binding() -> AnalyzerBinding:
    """Load the additive V4 API when its source implementation is available."""

    try:
        import leo.analysis.starlink.acquisition as acquisition_module
        from leo.analysis.qam.pilot_pnt_kalman import (
            PilotPntKalmanConfigV3,
            analyze_contiguous_pilot_pnt_kalman,
        )
        from leo.analysis.qam.pilot_pnt_kalman_v4 import (
            PilotPntKalmanConfigV4,
            analyze_contiguous_pilot_pnt_kalman_v4,
        )
        from leo.analysis.starlink.seeded_acquisition import (
            KnownPilotModeSeed,
            acquire_seeded_known_pilot_modes,
        )
        from leo.analysis.starlink.templates import qin_edge_pilot_frame
    except ImportError as error:
        raise RuntimeError(
            "PNT Kalman V4 API is unavailable; the canary harness is ready but a full "
            "replay must wait for analyze_contiguous_pilot_pnt_kalman_v4"
        ) from error

    config = PilotPntKalmanConfigV4()
    config_document = _plain(config)

    def analyze(samples: np.ndarray, sample_rate_hz: float, row: FrozenRow) -> Mapping[str, Any]:
        source = row.source
        rate = source.get("standard_v1_local_rate_hz_s")
        nominal_rate_hz_s = 0.0 if rate is None else float(rate)
        seed = KnownPilotModeSeed(
            nominal_epoch_sample=int(source["epoch_sample"]),
            nominal_absolute_cfo_hz=float(source["seed_cfo_hz"]),
            nominal_doppler_rate_hz_s=nominal_rate_hz_s,
            branch_id=str(source["source_branch_id"]),
            provenance_sha256=row.row_input_digest.removeprefix("sha256:"),
        )
        result = analyze_contiguous_pilot_pnt_kalman_v4(
            samples,
            sample_rate_hz,
            seed=seed,
            additional_seeds=(),
            edge=str(source["edge"]),
            maximum_residual_cfo_hz=2_000.0,
            expected_symbol_roll=0,
            config=config,
        )
        acquisition = result.acquisition
        if acquisition.config_digest != config.acquisition_config.digest:
            raise RuntimeError("V4 acquisition result/config digest mismatch")
        modes = tuple(acquisition.retained_modes)
        accepted = tuple(acquisition.accepted_modes)

        mode_ids = {id(mode): _candidate_id(mode) for mode in modes}
        alias_class_ids = _alias_class_ids(
            modes,
            cfo_tolerance_hz=(config.acquisition_config.cfo_alias_equivalence_tolerance_hz),
            rate_tolerance_hz_s=config.acquisition_config.cfo_alias_rate_tolerance_hz_s,
            timing_tolerance_samples=(config.acquisition_config.cfo_alias_timing_tolerance_samples),
        )
        accepted_ids = {_candidate_id(mode) for mode in accepted}
        proposals = []
        for mode in modes:
            mode_document = _plain(mode)
            proposals.append(
                {
                    "candidate_id": mode_ids[id(mode)],
                    "origin": _plain(mode.proposal_origin),
                    "decision": _plain(mode.decision),
                    "alias_class": alias_class_ids[id(mode)],
                    "mode": mode_document,
                }
            )
        independent_alias_classes: set[str] = set()
        tracks = []
        for mode_result in result.mode_results:
            mode = mode_result.mode
            identifier = _candidate_id(mode)
            alias_class = alias_class_ids[id(mode)]
            accepted_mode = identifier in accepted_ids
            independent = accepted_mode and alias_class not in independent_alias_classes
            if independent:
                independent_alias_classes.add(alias_class)
            tracks.append(
                {
                    "candidate_id": identifier,
                    "status": _plain(mode_result.tracking.status),
                    "phase_lock_qualified": bool(mode_result.phase_lock_qualified),
                    "published_independent": independent,
                    "supported_frame_count": int(mode_result.tracking.supported_frame_count),
                    "phase_lock_reason": str(mode_result.tracking.phase_lock_reason),
                    "mode_doppler_rate_hz_s": float(mode.doppler_rate_hz_s),
                    "applied_initial_doppler_rate_hz_s": float(mode.doppler_rate_hz_s),
                }
            )
        separation_suppressed = int(acquisition.separation_suppressed_count)
        limit_truncated = int(acquisition.candidate_limit_truncated_count)
        return {
            "acquisition_status": _plain(acquisition.status),
            "proposals": proposals,
            "sample_rate_hz": float(acquisition.sample_rate_hz),
            "sample_count": int(acquisition.sample_count),
            "frame_period_samples": float(acquisition.frame_period_samples),
            "block_starts": _plain(acquisition.block_starts),
            "searched_epoch_count": int(acquisition.searched_epoch_count),
            "searched_cfo_count": int(acquisition.searched_cfo_count),
            "evaluated_grid_point_count": int(acquisition.evaluated_grid_point_count),
            "evaluated_block_score_count": int(acquisition.evaluated_block_score_count),
            "trajectory_path_evaluated_count": int(acquisition.trajectory_path_evaluated_count),
            "trajectory_path_limit_truncated_count": int(
                acquisition.trajectory_path_limit_truncated_count
            ),
            "separation_suppressed_count": separation_suppressed,
            "candidate_limit_truncated_count": limit_truncated,
            "additional_seeds": _plain(acquisition.additional_seeds),
            "evaluated_seed_count": int(acquisition.evaluated_seed_count),
            "whole_window_rescore_candidate_count": int(
                acquisition.whole_window_rescore_candidate_count
            ),
            "whole_window_rescore_template_score_count": int(
                acquisition.whole_window_rescore_template_score_count
            ),
            "acquisition_config_digest": str(acquisition.config_digest),
            "alias_class_tolerances": {
                "cfo_hz": float(config.acquisition_config.cfo_alias_equivalence_tolerance_hz),
                "doppler_rate_hz_s": float(config.acquisition_config.cfo_alias_rate_tolerance_hz_s),
                "timing_samples": float(
                    config.acquisition_config.cfo_alias_timing_tolerance_samples
                ),
            },
            "exact_template_identity": _plain(acquisition.exact_template_identity),
            "conditional_control_template_identities": _plain(
                acquisition.conditional_control_template_identities
            ),
            "diagnostic_control_template_identities": _plain(
                acquisition.diagnostic_control_template_identities
            ),
            "presence_disposition": _plain(acquisition.presence_disposition),
            "code_specificity_disposition": _plain(acquisition.code_specificity_disposition),
            "cfo_alias_resolution_disposition": _plain(
                acquisition.cfo_alias_resolution_disposition
            ),
            "uniqueness_disposition": _plain(acquisition.uniqueness_disposition),
            "acquisition_thresholds_calibrated": bool(acquisition.thresholds_calibrated),
            "specificity_claimed": bool(acquisition.specificity_claimed),
            "acquisition_candidate_only": bool(acquisition.candidate_only),
            "global_fallback_attempted": bool(acquisition.global_fallback_attempted),
            "global_proposal_block_index": int(acquisition.global_proposal_block_index),
            "global_proposal_block_start_sample": (
                None
                if acquisition.global_proposal_block_start_sample is None
                else int(acquisition.global_proposal_block_start_sample)
            ),
            "global_proposal_block_stop_sample": (
                None
                if acquisition.global_proposal_block_stop_sample is None
                else int(acquisition.global_proposal_block_stop_sample)
            ),
            "global_proposal_sample_count": int(acquisition.global_proposal_sample_count),
            "global_proposal_symbols": _plain(config.acquisition_config.global_proposal_symbols),
            "global_proposal_symbol_count": int(acquisition.global_proposal_symbol_count),
            "global_proposal_frame_offset_count": int(
                acquisition.global_proposal_frame_offset_count
            ),
            "global_searched_epoch_count": int(acquisition.global_searched_epoch_count),
            "global_searched_cfo_count": int(acquisition.global_searched_cfo_count),
            "global_evaluated_grid_point_count": int(acquisition.global_evaluated_grid_point_count),
            "global_peak_count": int(acquisition.global_peak_count),
            "global_evaluated_block_score_count": int(
                acquisition.global_evaluated_block_score_count
            ),
            "global_trajectory_path_evaluated_count": int(
                acquisition.global_trajectory_path_evaluated_count
            ),
            "global_trajectory_path_limit_truncated_count": int(
                acquisition.global_trajectory_path_limit_truncated_count
            ),
            "global_separation_suppressed_count": int(
                acquisition.global_separation_suppressed_count
            ),
            "global_candidate_limit_truncated_count": int(
                acquisition.global_candidate_limit_truncated_count
            ),
            "retained_mode_ids": [_candidate_id(mode) for mode in modes],
            "accepted_mode_ids": sorted(accepted_ids),
            "tracks": tracks,
            "phase_thresholds_unchanged": (
                _plain(config.tracker_config) == _plain(PilotPntKalmanConfigV3())
            ),
            "numerical_status": _plain(result.numerical_status),
            "complete_mode_count": int(result.complete_mode_count),
            "phase_lock_qualified_mode_count": int(result.phase_lock_qualified_mode_count),
            "reason": str(result.reason),
            "seed": _plain(seed),
            "seed_rate_source": (
                "zero_when_standard_v1_local_rate_absent"
                if rate is None
                else "standard_v1_local_rate_hz_s"
            ),
        }

    inventory = _source_inventory(
        (
            analyze_contiguous_pilot_pnt_kalman_v4,
            acquire_seeded_known_pilot_modes,
            analyze_contiguous_pilot_pnt_kalman,
            acquisition_module._folded_anchor_score_grid,
            acquisition_module._circular_local_peak_indexes,
            qin_edge_pilot_frame,
        )
    )
    native_module = acquisition_module._native_acquisition
    if native_module is not None:
        native_path = Path(str(native_module.__file__)).resolve()
        try:
            native_name = str(native_path.relative_to(REPOSITORY_ROOT))
        except ValueError:
            native_name = native_path.name
        inventory[native_name] = _file_digest(native_path)
        inventory = dict(sorted(inventory.items()))
    runtime_inventory = {
        "folded_anchor_score_grid_backend": (
            acquisition_module._folded_anchor_score_grid_backend()
        ),
        "native_acquisition_loaded": native_module is not None,
    }
    return AnalyzerBinding(
        api_name="analyze_contiguous_pilot_pnt_kalman_v4",
        source_sha256=_value_digest(inventory),
        config_digest=_value_digest(config_document),
        config=config_document,
        analyze=analyze,
        source_inventory=inventory,
        runtime_inventory=runtime_inventory,
    )


def _validate_mode_trajectory(
    mode: Mapping[str, Any],
    *,
    block_starts: Sequence[int],
) -> None:
    """Require a complete, internally consistent selected-path audit row."""

    required = {
        "rank",
        "proposal_origin",
        "proposal_epoch_sample",
        "proposal_absolute_cfo_hz",
        "epoch_sample",
        "absolute_cfo_hz",
        "doppler_rate_hz_s",
        "canonical_cfo_hz",
        "cfo_alias_lift",
        "blocks",
        "trajectory_block_epoch_samples",
        "trajectory_block_epoch_residual_samples",
        "trajectory_block_absolute_cfo_hz",
        "trajectory_block_cfo_residual_hz",
        "trajectory_epoch_span_samples",
        "trajectory_max_adjacent_epoch_step_samples",
        "trajectory_epoch_dispersion_samples",
        "trajectory_epoch_fit_rms_samples",
        "trajectory_timing_rate_samples_s",
        "trajectory_cfo_span_hz",
        "trajectory_cfo_dispersion_hz",
        "trajectory_cfo_fit_rms_hz",
        "trajectory_cfo_rate_residual_hz_s",
        "trajectory_path_sha256",
        "trajectory_admissible",
    }
    missing = sorted(required - mode.keys())
    if missing:
        raise ValueError(f"V4 proposal lacks selected-trajectory fields: {missing}")
    path_digest = str(mode["trajectory_path_sha256"])
    if len(path_digest) != 64 or any(value not in "0123456789abcdef" for value in path_digest):
        raise ValueError("V4 trajectory path identity must be one lowercase SHA-256 digest")
    if not isinstance(mode["trajectory_admissible"], bool):
        raise ValueError("V4 trajectory admissibility must be boolean")

    blocks = mode["blocks"]
    trajectory_fields = (
        "trajectory_block_epoch_samples",
        "trajectory_block_epoch_residual_samples",
        "trajectory_block_absolute_cfo_hz",
        "trajectory_block_cfo_residual_hz",
    )
    if not isinstance(blocks, list) or any(
        not isinstance(mode[name], list) for name in trajectory_fields
    ):
        raise ValueError("V4 block and selected-trajectory evidence must be lists")
    expected_block_count = len(block_starts)
    if not blocks or any(
        len(values) != len(blocks) for values in (mode[name] for name in trajectory_fields)
    ):
        raise ValueError("V4 selected trajectory must provide one coordinate per block")
    if expected_block_count and len(blocks) != expected_block_count:
        raise ValueError("V4 selected trajectory does not match the configured block inventory")

    epoch_samples = tuple(int(value) for value in mode["trajectory_block_epoch_samples"])
    epoch_residuals = tuple(int(value) for value in mode["trajectory_block_epoch_residual_samples"])
    absolute_cfos_hz = tuple(float(value) for value in mode["trajectory_block_absolute_cfo_hz"])
    cfo_residuals_hz = tuple(float(value) for value in mode["trajectory_block_cfo_residual_hz"])
    if int(mode["trajectory_epoch_span_samples"]) != max(epoch_residuals) - min(epoch_residuals):
        raise ValueError("V4 trajectory epoch span is inconsistent with its block path")
    nonnegative_metrics = (
        int(mode["trajectory_epoch_span_samples"]),
        int(mode["trajectory_max_adjacent_epoch_step_samples"]),
        float(mode["trajectory_epoch_dispersion_samples"]),
        float(mode["trajectory_epoch_fit_rms_samples"]),
        float(mode["trajectory_cfo_span_hz"]),
        float(mode["trajectory_cfo_dispersion_hz"]),
        float(mode["trajectory_cfo_fit_rms_hz"]),
    )
    if min(nonnegative_metrics) < 0:
        raise ValueError("V4 trajectory span, dispersion, and fit metrics must be nonnegative")

    required_block = {
        "block_index",
        "start_sample",
        "stop_sample",
        "first_frame_start_sample",
        "projected_epoch_sample",
        "trajectory_epoch_sample",
        "trajectory_epoch_residual_samples",
        "absolute_cfo_hz",
        "trajectory_cfo_residual_hz",
        "acquire_score",
        "verify_score",
        "control_scores",
        "diagnostic_control_scores",
        "exact_minus_control_margin",
        "acquire_frame_support",
        "verify_frame_support",
        "control_frame_support",
        "diagnostic_control_frame_support",
        "frame_support",
        "passed_research_gate",
    }
    for index, block in enumerate(blocks):
        if not isinstance(block, dict) or not required_block <= block.keys():
            raise ValueError("each V4 block lacks trajectory scores or support evidence")
        if int(block["block_index"]) != index:
            raise ValueError("V4 trajectory block indexes must be contiguous")
        if block_starts and int(block["start_sample"]) != int(block_starts[index]):
            raise ValueError("V4 trajectory block start differs from acquisition inventory")
        if (
            int(block["trajectory_epoch_sample"]) != epoch_samples[index]
            or int(block["trajectory_epoch_residual_samples"]) != epoch_residuals[index]
            or not math.isclose(
                float(block["absolute_cfo_hz"]),
                absolute_cfos_hz[index],
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            or not math.isclose(
                float(block["trajectory_cfo_residual_hz"]),
                cfo_residuals_hz[index],
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        ):
            raise ValueError("V4 block evidence differs from its selected trajectory")
        control_scores = block["control_scores"]
        diagnostic_scores = block["diagnostic_control_scores"]
        control_support = block["control_frame_support"]
        diagnostic_support = block["diagnostic_control_frame_support"]
        if (
            not isinstance(control_scores, list)
            or not isinstance(diagnostic_scores, list)
            or not isinstance(control_support, list)
            or not isinstance(diagnostic_support, list)
            or len(control_scores) != len(control_support)
            or len(diagnostic_scores) != len(diagnostic_support)
        ):
            raise ValueError("V4 control scores and support inventories do not align")
        supports = (
            int(block["acquire_frame_support"]),
            int(block["verify_frame_support"]),
            int(block["frame_support"]),
            *(int(value) for value in control_support),
            *(int(value) for value in diagnostic_support),
        )
        if min(supports) < 0:
            raise ValueError("V4 block frame-support counts must be nonnegative")
        if not isinstance(block["passed_research_gate"], bool):
            raise ValueError("V4 per-block research decision must be boolean")


def canonical_v4_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the narrow evidence surface required by the canary.

    The V4 API adapter must expose all proposals, explicit truncation counts,
    retained/accepted-mode IDs, per-accepted-mode tracks,
    independent-publication decisions, and work counters.  This avoids
    inferring candidate accounting from a private implementation object.
    """

    evidence = _plain(value)
    if not isinstance(evidence, dict):
        raise TypeError("V4 evidence must be one object")
    required = {
        "acquisition_status",
        "proposals",
        "sample_rate_hz",
        "sample_count",
        "frame_period_samples",
        "block_starts",
        "searched_epoch_count",
        "searched_cfo_count",
        "evaluated_grid_point_count",
        "evaluated_block_score_count",
        "trajectory_path_evaluated_count",
        "trajectory_path_limit_truncated_count",
        "separation_suppressed_count",
        "candidate_limit_truncated_count",
        "additional_seeds",
        "evaluated_seed_count",
        "whole_window_rescore_candidate_count",
        "whole_window_rescore_template_score_count",
        "acquisition_config_digest",
        "alias_class_tolerances",
        "exact_template_identity",
        "conditional_control_template_identities",
        "diagnostic_control_template_identities",
        "presence_disposition",
        "code_specificity_disposition",
        "cfo_alias_resolution_disposition",
        "uniqueness_disposition",
        "acquisition_thresholds_calibrated",
        "specificity_claimed",
        "acquisition_candidate_only",
        "global_fallback_attempted",
        "global_proposal_block_index",
        "global_proposal_block_start_sample",
        "global_proposal_block_stop_sample",
        "global_proposal_sample_count",
        "global_proposal_symbols",
        "global_proposal_symbol_count",
        "global_proposal_frame_offset_count",
        "global_searched_epoch_count",
        "global_searched_cfo_count",
        "global_evaluated_grid_point_count",
        "global_peak_count",
        "global_evaluated_block_score_count",
        "global_trajectory_path_evaluated_count",
        "global_trajectory_path_limit_truncated_count",
        "global_separation_suppressed_count",
        "global_candidate_limit_truncated_count",
        "retained_mode_ids",
        "accepted_mode_ids",
        "tracks",
        "phase_thresholds_unchanged",
    }
    missing = sorted(required - evidence.keys())
    if missing:
        raise ValueError(f"V4 evidence is missing canary fields: {missing}")
    exact_identity = evidence["exact_template_identity"]
    conditional_identities = evidence["conditional_control_template_identities"]
    diagnostic_identities = evidence["diagnostic_control_template_identities"]
    if not isinstance(exact_identity, dict):
        raise ValueError("V4 exact template identity must be one object")
    if (
        not isinstance(conditional_identities, list)
        or not conditional_identities
        or not isinstance(diagnostic_identities, list)
        or not diagnostic_identities
    ):
        raise ValueError("V4 control template identities must be lists")
    if not str(evidence["acquisition_config_digest"]):
        raise ValueError("V4 acquisition config digest must be nonempty")
    alias_tolerances = evidence["alias_class_tolerances"]
    if not isinstance(alias_tolerances, dict) or set(alias_tolerances) != {
        "cfo_hz",
        "doppler_rate_hz_s",
        "timing_samples",
    }:
        raise ValueError("V4 alias-class tolerances must be an explicit complete inventory")
    cfo_alias_tolerance_hz = float(alias_tolerances["cfo_hz"])
    alias_rate_tolerance_hz_s = float(alias_tolerances["doppler_rate_hz_s"])
    alias_timing_tolerance_samples = float(alias_tolerances["timing_samples"])
    if (
        not all(
            math.isfinite(value)
            for value in (
                cfo_alias_tolerance_hz,
                alias_rate_tolerance_hz_s,
                alias_timing_tolerance_samples,
            )
        )
        or cfo_alias_tolerance_hz <= 0.0
        or alias_rate_tolerance_hz_s < 0.0
        or alias_timing_tolerance_samples < 0.0
    ):
        raise ValueError("V4 alias-class tolerances are outside their valid range")
    identity_fields = {
        "label",
        "template_sha256",
        "role",
        "gates_research_decision",
        "independently_reacquired",
    }
    identities = [exact_identity, *conditional_identities, *diagnostic_identities]
    if any(
        not isinstance(identity, dict) or not identity_fields <= identity.keys()
        for identity in identities
    ):
        raise ValueError("V4 template identity inventory is incomplete")
    if (
        exact_identity["role"] != "expected"
        or exact_identity["gates_research_decision"] is not True
        or exact_identity["independently_reacquired"] is not True
        or any(
            identity["role"] != "conditional_gate"
            or identity["gates_research_decision"] is not True
            or identity["independently_reacquired"] is not False
            for identity in conditional_identities
        )
        or any(
            identity["role"] != "orbit_breaking_diagnostic"
            or identity["gates_research_decision"] is not False
            or identity["independently_reacquired"] is not False
            for identity in diagnostic_identities
        )
    ):
        raise ValueError("V4 template roles do not preserve gating/diagnostic boundaries")
    if (
        evidence["acquisition_thresholds_calibrated"] is not False
        or evidence["specificity_claimed"] is not False
        or evidence["acquisition_candidate_only"] is not True
    ):
        raise ValueError("V4 acquisition evidence exceeds its uncalibrated candidate scope")
    proposals = evidence["proposals"]
    tracks = evidence["tracks"]
    retained = evidence["retained_mode_ids"]
    accepted = evidence["accepted_mode_ids"]
    if (
        not isinstance(proposals, list)
        or not isinstance(tracks, list)
        or not isinstance(retained, list)
        or not isinstance(accepted, list)
    ):
        raise ValueError("V4 proposals, retained/accepted modes, and tracks must be lists")
    block_starts = evidence["block_starts"]
    if not isinstance(block_starts, list) or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in block_starts
    ):
        raise ValueError("V4 block starts must be a nonnegative integer inventory")
    sample_rate_hz = float(evidence["sample_rate_hz"])
    sample_count = int(evidence["sample_count"])
    frame_period_samples = float(evidence["frame_period_samples"])
    if (
        not math.isfinite(sample_rate_hz)
        or sample_rate_hz <= 0.0
        or sample_count < 0
        or not math.isfinite(frame_period_samples)
        or frame_period_samples <= 0.0
    ):
        raise ValueError("V4 sample and frame-period metadata are outside their valid range")
    proposal_ids = []
    proposal_origins = []
    proposal_decisions = []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            raise ValueError("each V4 proposal must be an object")
        required_proposal = {"candidate_id", "origin", "decision", "alias_class", "mode"}
        if not required_proposal <= proposal.keys():
            raise ValueError(
                "each V4 proposal needs ID, origin, decision, alias class, and mode evidence"
            )
        mode = proposal["mode"]
        source_and_window_fields = {
            "source_seed_index",
            "source_branch_id",
            "source_provenance_sha256",
            "source_nominal_epoch_sample",
            "source_nominal_absolute_cfo_hz",
            "whole_window_verify_score",
            "whole_window_control_scores",
            "whole_window_diagnostic_control_scores",
            "whole_window_exact_minus_control_margin",
            "whole_window_frame_support",
            "whole_window_consistent_with_blocks",
        }
        if not isinstance(mode, dict) or not source_and_window_fields <= mode.keys():
            raise ValueError("each V4 proposal lacks source-seed or whole-window evidence")
        _validate_mode_trajectory(mode, block_starts=block_starts)
        proposal_ids.append(str(proposal["candidate_id"]))
        proposal_origins.append(str(proposal["origin"]))
        proposal_decisions.append(str(proposal["decision"]))
    expected_alias_classes = _alias_class_ids(
        [proposal["mode"] for proposal in proposals],
        cfo_tolerance_hz=cfo_alias_tolerance_hz,
        rate_tolerance_hz_s=alias_rate_tolerance_hz_s,
        timing_tolerance_samples=alias_timing_tolerance_samples,
    )
    for left_index, left in enumerate(proposals):
        for right in proposals[left_index + 1 :]:
            expected_same = (
                expected_alias_classes[id(left["mode"])]
                == expected_alias_classes[id(right["mode"])]
            )
            reported_same = str(left["alias_class"]) == str(right["alias_class"])
            if expected_same != reported_same:
                raise ValueError("V4 alias classes do not match full-trajectory equivalence")
    if len(set(proposal_ids)) != len(proposal_ids):
        raise ValueError("V4 candidate IDs are not unique within the row")
    searched_epoch_count = int(evidence["searched_epoch_count"])
    searched_cfo_count = int(evidence["searched_cfo_count"])
    grid_count = int(evidence["evaluated_grid_point_count"])
    block_score_count = int(evidence["evaluated_block_score_count"])
    trajectory_path_evaluated_count = int(evidence["trajectory_path_evaluated_count"])
    trajectory_path_truncated_count = int(evidence["trajectory_path_limit_truncated_count"])
    suppressed = int(evidence["separation_suppressed_count"])
    truncated = int(evidence["candidate_limit_truncated_count"])
    global_attempted = evidence["global_fallback_attempted"]
    if not isinstance(global_attempted, bool):
        raise ValueError("V4 global fallback attempt flag must be boolean")
    proposal_block_index_value = evidence["global_proposal_block_index"]
    if isinstance(proposal_block_index_value, bool) or not isinstance(
        proposal_block_index_value, int
    ):
        raise ValueError("V4 global proposal block index must be an integer")
    global_proposal_block_index = proposal_block_index_value
    proposal_start_value = evidence["global_proposal_block_start_sample"]
    proposal_stop_value = evidence["global_proposal_block_stop_sample"]
    if any(
        value is not None and (isinstance(value, bool) or not isinstance(value, int))
        for value in (proposal_start_value, proposal_stop_value)
    ):
        raise ValueError("V4 global proposal block bounds must be integer samples or null")
    global_proposal_sample_count = int(evidence["global_proposal_sample_count"])
    global_proposal_symbol_count = int(evidence["global_proposal_symbol_count"])
    global_proposal_frame_offset_count = int(evidence["global_proposal_frame_offset_count"])
    global_proposal_symbols = evidence["global_proposal_symbols"]
    if (
        not isinstance(global_proposal_symbols, list)
        or not global_proposal_symbols
        or len(set(global_proposal_symbols)) != len(global_proposal_symbols)
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in global_proposal_symbols
        )
    ):
        raise ValueError("V4 global proposal symbols must be a unique integer inventory")
    if global_proposal_block_index != 0:
        raise ValueError("V4 global proposal block must remain capture-relative block zero")
    if (
        min(
            global_proposal_sample_count,
            global_proposal_symbol_count,
            global_proposal_frame_offset_count,
        )
        < 0
    ):
        raise ValueError("V4 global proposal work counts must be nonnegative")
    global_searched_epoch_count = int(evidence["global_searched_epoch_count"])
    global_searched_cfo_count = int(evidence["global_searched_cfo_count"])
    global_grid_count = int(evidence["global_evaluated_grid_point_count"])
    global_peak_count = int(evidence["global_peak_count"])
    global_block_score_count = int(evidence["global_evaluated_block_score_count"])
    global_trajectory_path_evaluated_count = int(evidence["global_trajectory_path_evaluated_count"])
    global_trajectory_path_truncated_count = int(
        evidence["global_trajectory_path_limit_truncated_count"]
    )
    global_suppressed = int(evidence["global_separation_suppressed_count"])
    global_truncated = int(evidence["global_candidate_limit_truncated_count"])
    counts = (
        searched_epoch_count,
        searched_cfo_count,
        grid_count,
        block_score_count,
        trajectory_path_evaluated_count,
        trajectory_path_truncated_count,
        suppressed,
        truncated,
        global_searched_epoch_count,
        global_searched_cfo_count,
        global_grid_count,
        global_peak_count,
        global_block_score_count,
        global_trajectory_path_evaluated_count,
        global_trajectory_path_truncated_count,
        global_suppressed,
        global_truncated,
    )
    if min(counts) < 0:
        raise ValueError("V4 acquisition work counts must be nonnegative")
    additional_seeds = evidence["additional_seeds"]
    evaluated_seed_count = int(evidence["evaluated_seed_count"])
    whole_window_candidate_count = int(evidence["whole_window_rescore_candidate_count"])
    whole_window_template_score_count = int(evidence["whole_window_rescore_template_score_count"])
    if not isinstance(additional_seeds, list) or additional_seeds:
        raise ValueError("frozen V4 replay requires an explicit empty additional-seed inventory")
    if evaluated_seed_count != 1:
        raise ValueError("frozen V4 replay must evaluate exactly its one provenance-bound seed")
    template_count = 1 + len(conditional_identities) + len(diagnostic_identities)
    if (
        whole_window_candidate_count < 0
        or whole_window_template_score_count != whole_window_candidate_count * template_count
    ):
        raise ValueError("V4 whole-window rescore accounting is incomplete")
    local_serialized_count = sum(origin != "global_fallback" for origin in proposal_origins)
    global_serialized_count = sum(origin == "global_fallback" for origin in proposal_origins)
    block_count = len(block_starts)
    if grid_count != searched_epoch_count * searched_cfo_count:
        raise ValueError("V4 local grid count does not match searched epoch/CFO dimensions")
    if block_count:
        if block_score_count != grid_count * block_count:
            raise ValueError(
                "V4 local block-score count is not the unique cached even-lattice inventory"
            )
        if trajectory_path_evaluated_count < grid_count:
            raise ValueError("V4 local trajectory search did not evaluate every grid anchor")
    elif any(
        (
            grid_count,
            block_score_count,
            trajectory_path_evaluated_count,
            trajectory_path_truncated_count,
        )
    ):
        raise ValueError("V4 reported local work without a block inventory")
    if grid_count != local_serialized_count + suppressed + truncated:
        raise ValueError(
            "V4 local grid count does not equal local retained plus separation-suppressed plus "
            "candidate-limit-truncated proposals"
        )
    if global_peak_count != global_serialized_count + global_suppressed + global_truncated:
        raise ValueError(
            "V4 global peak count does not equal global retained plus "
            "global-separation-suppressed plus global-candidate-limit-truncated proposals"
        )
    global_counts = (
        global_searched_epoch_count,
        global_searched_cfo_count,
        global_grid_count,
        global_peak_count,
        global_block_score_count,
        global_trajectory_path_evaluated_count,
        global_trajectory_path_truncated_count,
        global_suppressed,
        global_truncated,
    )
    if not global_attempted:
        if any(global_counts) or global_serialized_count:
            raise ValueError("V4 reported global work without attempting global fallback")
        if (
            proposal_start_value is not None
            or proposal_stop_value is not None
            or global_proposal_sample_count
            or global_proposal_symbol_count
            or global_proposal_frame_offset_count
        ):
            raise ValueError("V4 reported global proposal work without attempting fallback")
    else:
        if (
            not block_starts
            or global_proposal_block_index >= len(block_starts)
            or proposal_start_value != block_starts[global_proposal_block_index]
            or proposal_stop_value is None
            or proposal_stop_value <= proposal_start_value
            or proposal_stop_value > sample_count
            or global_proposal_sample_count != proposal_stop_value - proposal_start_value
            or global_proposal_symbol_count != len(global_proposal_symbols)
        ):
            raise ValueError("V4 global proposal block or symbol accounting is inconsistent")
        expected_frame_offset_count = 0
        while round(expected_frame_offset_count * frame_period_samples) < (
            global_proposal_sample_count
        ):
            expected_frame_offset_count += 1
        if global_proposal_frame_offset_count != expected_frame_offset_count:
            raise ValueError("V4 global proposal frame-offset count is inconsistent")
    if global_attempted and global_grid_count != (
        global_searched_epoch_count * global_searched_cfo_count
    ):
        raise ValueError("V4 global grid count does not match searched epoch/CFO dimensions")
    global_refinement_coordinate_pair_count = 0
    if block_count:
        if global_block_score_count % block_count:
            raise ValueError(
                "V4 global block-score count is not a complete unique even-lattice inventory"
            )
        global_refinement_coordinate_pair_count = global_block_score_count // block_count
        if global_refinement_coordinate_pair_count < global_serialized_count:
            raise ValueError("V4 global block-score cache does not cover every retained peak")
        if global_trajectory_path_evaluated_count < global_serialized_count:
            raise ValueError("V4 global trajectory search did not evaluate every retained peak")
    trajectory_path_universe_count = (
        trajectory_path_evaluated_count + trajectory_path_truncated_count
    )
    global_trajectory_path_universe_count = (
        global_trajectory_path_evaluated_count + global_trajectory_path_truncated_count
    )
    retained_ids = tuple(str(value) for value in retained)
    if len(set(retained_ids)) != len(retained_ids) or set(retained_ids) != set(proposal_ids):
        raise ValueError("V4 retained modes must equal the unique serialized proposal IDs")
    accepted_ids = tuple(str(value) for value in accepted)
    if len(set(accepted_ids)) != len(accepted_ids) or not set(accepted_ids) <= set(retained_ids):
        raise ValueError("V4 accepted modes must be unique retained mode IDs")
    dispositions = (
        str(evidence["presence_disposition"]),
        str(evidence["code_specificity_disposition"]),
        str(evidence["cfo_alias_resolution_disposition"]),
        str(evidence["uniqueness_disposition"]),
    )
    if evidence["acquisition_status"] == "insufficient":
        expected_dispositions = {("insufficient",) * 4}
    elif accepted_ids:
        expected_dispositions = {
            ("uncalibrated_candidate", "ambiguous", "unresolved", "unresolved"),
            ("uncalibrated_candidate", "ambiguous", "unresolved", "ambiguous"),
        }
    else:
        expected_dispositions = {
            ("no_research_candidate", "unassessed", "unassessed", "unassessed")
        }
    if dispositions not in expected_dispositions:
        raise ValueError("V4 acquisition dispositions overstate the admitted evidence")
    track_ids = []
    proposal_by_id = {str(proposal["candidate_id"]): proposal for proposal in proposals}
    for track in tracks:
        if not isinstance(track, dict):
            raise ValueError("each V4 track must be an object")
        if (
            not {
                "candidate_id",
                "status",
                "phase_lock_qualified",
                "published_independent",
                "mode_doppler_rate_hz_s",
                "applied_initial_doppler_rate_hz_s",
            }
            <= track.keys()
        ):
            raise ValueError("each V4 track lacks canary decision fields")
        if str(track["candidate_id"]) not in retained_ids:
            raise ValueError("V4 track references a mode that was not retained")
        candidate = proposal_by_id[str(track["candidate_id"])]
        mode_rate_hz_s = float(candidate["mode"]["doppler_rate_hz_s"])
        reported_mode_rate_hz_s = float(track["mode_doppler_rate_hz_s"])
        applied_rate_hz_s = float(track["applied_initial_doppler_rate_hz_s"])
        if not (
            math.isclose(mode_rate_hz_s, reported_mode_rate_hz_s, rel_tol=0.0, abs_tol=0.0)
            and math.isclose(mode_rate_hz_s, applied_rate_hz_s, rel_tol=0.0, abs_tol=0.0)
        ):
            raise ValueError("V4 tracker initial Doppler rate does not match its accepted mode")
        track_ids.append(str(track["candidate_id"]))
    if len(set(track_ids)) != len(track_ids) or set(track_ids) != set(accepted_ids):
        raise ValueError("V4 must report exactly one track result for every accepted mode")
    if not isinstance(evidence["phase_thresholds_unchanged"], bool):
        raise ValueError("V4 phase-threshold parity must be explicit")
    evidence["candidate_accounting_complete"] = True
    evidence["source_seed_accounting_complete"] = True
    evidence["whole_window_accounting_complete"] = True
    evidence["trajectory_accounting_complete"] = True
    evidence["global_proposal_accounting_complete"] = True
    evidence["tracker_initial_rate_accounting_complete"] = True
    evidence["research_claim_boundaries_preserved"] = True
    evidence["scientific_qualification_claimed"] = False
    evidence["serialized_proposal_count"] = len(proposals)
    evidence["local_serialized_proposal_count"] = local_serialized_count
    evidence["global_serialized_proposal_count"] = global_serialized_count
    evidence["unserialized_proposal_count"] = (
        suppressed + truncated + global_suppressed + global_truncated
    )
    evidence["proposal_count"] = grid_count + global_peak_count
    evidence["global_refinement_coordinate_pair_count"] = global_refinement_coordinate_pair_count
    evidence["proposal_origin_counts"] = {
        origin: proposal_origins.count(origin) for origin in sorted(set(proposal_origins))
    }
    evidence["component_decision_counts"] = {
        decision: proposal_decisions.count(decision) for decision in sorted(set(proposal_decisions))
    }
    evidence["work_counters"] = {
        "local": {
            "searched_epoch_count": searched_epoch_count,
            "searched_cfo_count": searched_cfo_count,
            "block_count": block_count,
            "evaluated_grid_point_count": grid_count,
            "evaluated_block_score_count": block_score_count,
            "unique_even_lattice_score_count": block_score_count,
            "trajectory_path_evaluated_count": trajectory_path_evaluated_count,
            "trajectory_path_limit_truncated_count": trajectory_path_truncated_count,
            "trajectory_path_universe_count": trajectory_path_universe_count,
            "separation_suppressed_count": suppressed,
            "candidate_limit_truncated_count": truncated,
        },
        "global": {
            "fallback_attempted": global_attempted,
            "proposal_block_index": global_proposal_block_index,
            "proposal_block_start_sample": proposal_start_value,
            "proposal_block_stop_sample": proposal_stop_value,
            "proposal_sample_count": global_proposal_sample_count,
            "proposal_symbols": list(global_proposal_symbols),
            "proposal_symbol_count": global_proposal_symbol_count,
            "proposal_frame_offset_count": global_proposal_frame_offset_count,
            "searched_epoch_count": global_searched_epoch_count,
            "searched_cfo_count": global_searched_cfo_count,
            "evaluated_grid_point_count": global_grid_count,
            "peak_count": global_peak_count,
            "refinement_coordinate_pair_count": global_refinement_coordinate_pair_count,
            "evaluated_block_score_count": global_block_score_count,
            "unique_even_lattice_score_count": global_block_score_count,
            "unique_exact_pair_block_score_count": global_block_score_count,
            "trajectory_path_evaluated_count": (global_trajectory_path_evaluated_count),
            "trajectory_path_limit_truncated_count": (global_trajectory_path_truncated_count),
            "trajectory_path_universe_count": global_trajectory_path_universe_count,
            "separation_suppressed_count": global_suppressed,
            "candidate_limit_truncated_count": global_truncated,
        },
    }
    evidence["tracked_mode_count"] = sum(track["status"] == "complete" for track in tracks)
    evidence["phase_lock_count"] = sum(bool(track["phase_lock_qualified"]) for track in tracks)
    evidence["accepted_tracked_mode_count"] = sum(
        track["status"] == "complete" and str(track["candidate_id"]) in accepted_ids
        for track in tracks
    )
    evidence["accepted_phase_lock_count"] = sum(
        bool(track["phase_lock_qualified"]) and str(track["candidate_id"]) in accepted_ids
        for track in tracks
    )
    evidence["published_independent_track_count"] = sum(
        track["status"] == "complete" and bool(track["published_independent"]) for track in tracks
    )
    tracks_by_id = {str(track["candidate_id"]): track for track in tracks}
    evidence["component_inventory"] = [
        {
            "candidate_id": str(proposal["candidate_id"]),
            "origin": str(proposal["origin"]),
            "decision": str(proposal["decision"]),
            "alias_class": str(proposal["alias_class"]),
            "source_seed_index": int(proposal["mode"]["source_seed_index"]),
            "source_branch_id": str(proposal["mode"]["source_branch_id"]),
            "source_provenance_sha256": str(proposal["mode"]["source_provenance_sha256"]),
            "proposal_epoch_sample": int(proposal["mode"]["proposal_epoch_sample"]),
            "proposal_absolute_cfo_hz": float(proposal["mode"]["proposal_absolute_cfo_hz"]),
            "trajectory_reference_epoch_sample": int(proposal["mode"]["epoch_sample"]),
            "trajectory_reference_absolute_cfo_hz": float(proposal["mode"]["absolute_cfo_hz"]),
            "doppler_rate_hz_s": float(proposal["mode"]["doppler_rate_hz_s"]),
            "trajectory_block_epoch_samples": list(
                proposal["mode"]["trajectory_block_epoch_samples"]
            ),
            "trajectory_block_epoch_residual_samples": list(
                proposal["mode"]["trajectory_block_epoch_residual_samples"]
            ),
            "trajectory_block_absolute_cfo_hz": list(
                proposal["mode"]["trajectory_block_absolute_cfo_hz"]
            ),
            "trajectory_block_cfo_residual_hz": list(
                proposal["mode"]["trajectory_block_cfo_residual_hz"]
            ),
            "trajectory_epoch_span_samples": int(proposal["mode"]["trajectory_epoch_span_samples"]),
            "trajectory_max_adjacent_epoch_step_samples": int(
                proposal["mode"]["trajectory_max_adjacent_epoch_step_samples"]
            ),
            "trajectory_epoch_dispersion_samples": float(
                proposal["mode"]["trajectory_epoch_dispersion_samples"]
            ),
            "trajectory_epoch_fit_rms_samples": float(
                proposal["mode"]["trajectory_epoch_fit_rms_samples"]
            ),
            "trajectory_timing_rate_samples_s": float(
                proposal["mode"]["trajectory_timing_rate_samples_s"]
            ),
            "trajectory_cfo_span_hz": float(proposal["mode"]["trajectory_cfo_span_hz"]),
            "trajectory_cfo_dispersion_hz": float(proposal["mode"]["trajectory_cfo_dispersion_hz"]),
            "trajectory_cfo_fit_rms_hz": float(proposal["mode"]["trajectory_cfo_fit_rms_hz"]),
            "trajectory_cfo_rate_residual_hz_s": float(
                proposal["mode"]["trajectory_cfo_rate_residual_hz_s"]
            ),
            "trajectory_path_sha256": str(proposal["mode"]["trajectory_path_sha256"]),
            "trajectory_admissible": bool(proposal["mode"]["trajectory_admissible"]),
            "whole_window_verify_score": (
                None
                if proposal["mode"]["whole_window_verify_score"] is None
                else float(proposal["mode"]["whole_window_verify_score"])
            ),
            "whole_window_exact_minus_control_margin": (
                None
                if proposal["mode"]["whole_window_exact_minus_control_margin"] is None
                else float(proposal["mode"]["whole_window_exact_minus_control_margin"])
            ),
            "whole_window_frame_support": int(proposal["mode"]["whole_window_frame_support"]),
            "whole_window_consistent_with_blocks": bool(
                proposal["mode"]["whole_window_consistent_with_blocks"]
            ),
            "accepted": str(proposal["candidate_id"]) in accepted_ids,
            "track_status": tracks_by_id.get(str(proposal["candidate_id"]), {}).get("status"),
            "phase_lock_qualified": tracks_by_id.get(str(proposal["candidate_id"]), {}).get(
                "phase_lock_qualified"
            ),
            "applied_initial_doppler_rate_hz_s": tracks_by_id.get(
                str(proposal["candidate_id"]), {}
            ).get("applied_initial_doppler_rate_hz_s"),
        }
        for proposal in proposals
    ]
    evidence["evidence_digest"] = _value_digest(evidence)
    return evidence


def checkpoint_path(output_root: Path, row: FrozenRow) -> Path:
    return output_root / "rows" / f"{row.index:06d}-{row.row_key[7:19]}.json"


def _checkpoint_identity(
    frozen: FrozenInput,
    row: FrozenRow,
    manifest_digest: str,
    binding: AnalyzerBinding,
) -> dict[str, Any]:
    return {
        "frozen_input_sha256": frozen.digest,
        "recording_manifest_sha256": manifest_digest,
        "harness_source_sha256": _file_digest(Path(__file__).resolve()),
        "analyzer_api": binding.api_name,
        "analyzer_source_sha256": binding.source_sha256,
        "analyzer_source_inventory": binding.source_inventory,
        "analyzer_runtime_inventory": binding.runtime_inventory,
        "analyzer_config_digest": binding.config_digest,
        "row_index": row.index,
        "row_key": row.row_key,
        "row_input_digest": row.row_input_digest,
    }


def reusable_checkpoint(path: Path, identity: Mapping[str, Any]) -> bool:
    if not path.is_file():
        return False
    try:
        document = _json_object(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    evidence = document.get("v4")
    if not isinstance(evidence, dict):
        return False
    recorded_digest = evidence.get("evidence_digest")
    digest_input = dict(evidence)
    digest_input.pop("evidence_digest", None)
    return bool(
        document.get("schema") == ROW_SCHEMA
        and document.get("execution_status") == "complete"
        and document.get("identity") == dict(identity)
        and evidence.get("candidate_accounting_complete") is True
        and recorded_digest == _value_digest(digest_input)
    )


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            json.dump(_plain(document), destination, indent=2, sort_keys=True, allow_nan=False)
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _validate_output_root(output_root: Path, capture_root: Path | None) -> None:
    resolved = output_root.resolve()
    forbidden = [QNAP_ROOT.resolve()]
    if capture_root is not None:
        forbidden.append(capture_root.resolve())
    for root in forbidden:
        if resolved == root or root in resolved.parents:
            raise ValueError(f"canary output root is read-only by policy: {resolved}")


def _baseline(row: FrozenRow) -> dict[str, Any]:
    source = row.source
    return {
        "scope": source["scope"],
        "stream": source["stream"],
        "receiver": int(source["receiver"]),
        "edge": source["edge"],
        "start_time_s": float(source["start_time_s"]),
        "source_probe_sample_start": int(source["source_probe_sample_start"]),
        "source_trajectory_id": source["source_trajectory_id"],
        "epoch_sample": int(source["epoch_sample"]),
        "seed_cfo_hz": float(source["seed_cfo_hz"]),
        "standard_v1_qualified": bool(source["standard_v1_qualified"]),
        "v2_status": source["v2_status"],
        "v2_frequency_update_count": int(source["v2_frequency_update_count"]),
        "v2_phase_lock_qualified": bool(source["v2_phase_lock_qualified"]),
        "v3_status": source["v3_status"],
        "v3_phase_lock_qualified": bool(source["v3_phase_lock_qualified"]),
    }


def analyze_row(
    *,
    frozen: FrozenInput,
    row: FrozenRow,
    reader: FrozenCi16Reader,
    binding: AnalyzerBinding,
) -> dict[str, Any]:
    samples, receipts = reader.read_complex(
        str(row.source["stream"]),
        int(row.source["receiver"]),
        row.sample_start,
        WINDOW_SAMPLE_COUNT,
    )
    evidence = canonical_v4_evidence(binding.analyze(samples, reader.sample_rate_hz, row))
    identity = _checkpoint_identity(frozen, row, reader.manifest_digest, binding)
    return {
        "schema": ROW_SCHEMA,
        "identity": identity,
        "execution_status": "complete",
        "baseline": _baseline(row),
        "verified_iq_chunks": [dataclasses.asdict(receipt) for receipt in receipts],
        "v4": evidence,
    }


def _execution_error(
    *,
    frozen: FrozenInput,
    row: FrozenRow,
    reader: FrozenCi16Reader,
    binding: AnalyzerBinding,
    error: Exception,
) -> dict[str, Any]:
    return {
        "schema": ROW_SCHEMA,
        "identity": _checkpoint_identity(frozen, row, reader.manifest_digest, binding),
        "execution_status": "execution_error",
        "baseline": _baseline(row),
        "error_type": type(error).__name__,
        "error": str(error),
        "candidate_accounting_status": "unavailable_due_execution_error",
    }


def evaluate_published_gates(
    *,
    frozen: FrozenInput,
    cohorts: Mapping[str, Sequence[str]],
    checkpoints: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_key = {
        str(document.get("identity", {}).get("row_key")): document
        for document in checkpoints
        if document.get("execution_status") == "complete"
    }
    if len(by_key) != len(frozen.rows):
        return {
            "status": "not_estimable",
            "reason": "complete frozen-population row checkpoints are required",
            "expected_row_count": len(frozen.rows),
            "completed_row_count": len(by_key),
        }

    def selected(key: str) -> bool:
        return bool(by_key[key]["v4"]["accepted_mode_ids"])

    def tracked(key: str) -> bool:
        return int(by_key[key]["v4"]["accepted_tracked_mode_count"]) > 0

    def independent_tracks(key: str) -> int:
        return int(by_key[key]["v4"]["published_independent_track_count"])

    standard = cohorts["standard_qualified_controls"]
    v2_phase = cohorts["v2_phase_qualified_controls"]
    robust = cohorts["robust_v3_losses"]
    aliases = cohorts["one_update_aliases"]
    nulls = cohorts["matched_alias_null_peers"]
    observations = {
        "population_rows_accounted": len(by_key),
        "standard_qualified_controls_tracked": sum(tracked(key) for key in standard),
        "v2_phase_qualified_controls_tracked": sum(tracked(key) for key in v2_phase),
        "robust_v3_losses_selected": sum(selected(key) for key in robust),
        "robust_v3_losses_tracked": sum(tracked(key) for key in robust),
        "one_update_alias_independent_tracks": sum(independent_tracks(key) for key in aliases),
        "matched_alias_null_peers_selected": sum(selected(key) for key in nulls),
        "matched_alias_null_peers_tracked": sum(tracked(key) for key in nulls),
        "serialized_proposal_count": sum(
            int(document["v4"]["serialized_proposal_count"]) for document in by_key.values()
        ),
        "local_serialized_proposal_count": sum(
            int(document["v4"]["local_serialized_proposal_count"]) for document in by_key.values()
        ),
        "global_serialized_proposal_count": sum(
            int(document["v4"]["global_serialized_proposal_count"]) for document in by_key.values()
        ),
        "separation_suppressed_count": sum(
            int(document["v4"]["separation_suppressed_count"]) for document in by_key.values()
        ),
        "candidate_limit_truncated_count": sum(
            int(document["v4"]["candidate_limit_truncated_count"]) for document in by_key.values()
        ),
        "global_fallback_attempted_row_count": sum(
            bool(document["v4"]["global_fallback_attempted"]) for document in by_key.values()
        ),
        "global_evaluated_grid_point_count": sum(
            int(document["v4"]["global_evaluated_grid_point_count"]) for document in by_key.values()
        ),
        "global_peak_count": sum(
            int(document["v4"]["global_peak_count"]) for document in by_key.values()
        ),
        "trajectory_path_evaluated_count": sum(
            int(document["v4"]["trajectory_path_evaluated_count"]) for document in by_key.values()
        ),
        "trajectory_path_limit_truncated_count": sum(
            int(document["v4"]["trajectory_path_limit_truncated_count"])
            for document in by_key.values()
        ),
        "global_trajectory_path_evaluated_count": sum(
            int(document["v4"]["global_trajectory_path_evaluated_count"])
            for document in by_key.values()
        ),
        "global_trajectory_path_limit_truncated_count": sum(
            int(document["v4"]["global_trajectory_path_limit_truncated_count"])
            for document in by_key.values()
        ),
        "global_separation_suppressed_count": sum(
            int(document["v4"]["global_separation_suppressed_count"])
            for document in by_key.values()
        ),
        "global_candidate_limit_truncated_count": sum(
            int(document["v4"]["global_candidate_limit_truncated_count"])
            for document in by_key.values()
        ),
        "proposal_count": sum(
            int(document["v4"]["proposal_count"]) for document in by_key.values()
        ),
        "evaluated_seed_count": sum(
            int(document["v4"]["evaluated_seed_count"]) for document in by_key.values()
        ),
        "whole_window_rescore_candidate_count": sum(
            int(document["v4"]["whole_window_rescore_candidate_count"])
            for document in by_key.values()
        ),
        "whole_window_rescore_template_score_count": sum(
            int(document["v4"]["whole_window_rescore_template_score_count"])
            for document in by_key.values()
        ),
        "phase_thresholds_unchanged": all(
            document["v4"]["phase_thresholds_unchanged"] for document in by_key.values()
        ),
        "research_claim_boundaries_preserved": all(
            document["v4"]["research_claim_boundaries_preserved"]
            and not document["v4"]["scientific_qualification_claimed"]
            for document in by_key.values()
        ),
    }
    baseline_by_key = {row.row_key: row for row in frozen.rows}
    new_phase = sorted(
        key
        for key, document in by_key.items()
        if int(document["v4"]["accepted_phase_lock_count"]) > 0
        and not bool(baseline_by_key[key].source["v3_phase_lock_qualified"])
    )
    requirements = PUBLISHED_GATES["requirements"]
    checks = {
        "all_rows_and_proposals_accounted": (
            observations["population_rows_accounted"] == FROZEN_ROW_COUNT
            and observations["proposal_count"]
            == observations["serialized_proposal_count"]
            + observations["separation_suppressed_count"]
            + observations["candidate_limit_truncated_count"]
            + observations["global_separation_suppressed_count"]
            + observations["global_candidate_limit_truncated_count"]
            and observations["evaluated_seed_count"] == FROZEN_ROW_COUNT
            and all(
                document["v4"]["source_seed_accounting_complete"]
                and document["v4"]["whole_window_accounting_complete"]
                and document["v4"]["trajectory_accounting_complete"]
                and document["v4"]["tracker_initial_rate_accounting_complete"]
                for document in by_key.values()
            )
        ),
        "standard_qualified_controls_tracked": (
            observations["standard_qualified_controls_tracked"]
            == requirements["standard_qualified_controls_tracked"]
        ),
        "v2_phase_qualified_controls_tracked": (
            observations["v2_phase_qualified_controls_tracked"]
            == requirements["v2_phase_qualified_controls_tracked"]
        ),
        "robust_v3_losses_selected": (
            observations["robust_v3_losses_selected"] == requirements["robust_v3_losses_selected"]
        ),
        "robust_v3_losses_tracked": (
            observations["robust_v3_losses_tracked"] == requirements["robust_v3_losses_tracked"]
        ),
        "one_update_alias_independent_tracks": (
            observations["one_update_alias_independent_tracks"]
            == requirements["one_update_alias_independent_tracks"]
        ),
        "matched_alias_null_peers_selected": (
            observations["matched_alias_null_peers_selected"]
            == requirements["matched_alias_null_peers_selected"]
        ),
        "matched_alias_null_peers_tracked": (
            observations["matched_alias_null_peers_tracked"]
            == requirements["matched_alias_null_peers_tracked"]
        ),
        "phase_thresholds_unchanged": (
            observations["phase_thresholds_unchanged"] == requirements["phase_thresholds_unchanged"]
        ),
        "research_claim_boundaries_preserved": (
            observations["research_claim_boundaries_preserved"]
            == requirements["research_claim_boundaries_preserved"]
        ),
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "observations": observations,
        "new_phase_qualified_row_keys_for_review": new_phase,
        "automatic_phase_promotion": False,
    }


def _index_document(
    *,
    frozen: FrozenInput,
    reader: FrozenCi16Reader,
    binding: AnalyzerBinding,
    checkpoints: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    complete = sum(document.get("execution_status") == "complete" for document in checkpoints)
    errors = sum(document.get("execution_status") == "execution_error" for document in checkpoints)
    return {
        "schema": INDEX_SCHEMA,
        "frozen_input_sha256": frozen.digest,
        "recording_manifest_sha256": reader.manifest_digest,
        "harness_source_sha256": _file_digest(Path(__file__).resolve()),
        "analyzer_api": binding.api_name,
        "analyzer_source_sha256": binding.source_sha256,
        "analyzer_source_inventory": binding.source_inventory,
        "analyzer_runtime_inventory": binding.runtime_inventory,
        "analyzer_config_digest": binding.config_digest,
        "population_row_count": len(frozen.rows),
        "checkpoint_count": len(checkpoints),
        "completed_row_count": complete,
        "execution_error_count": errors,
        "pending_row_count": len(frozen.rows) - len(checkpoints),
        "checkpoint_row_keys": sorted(
            str(document.get("identity", {}).get("row_key")) for document in checkpoints
        ),
        "checkpoint_document_sha256": {
            str(document.get("identity", {}).get("row_key")): _value_digest(document)
            for document in sorted(
                checkpoints,
                key=lambda value: str(value.get("identity", {}).get("row_key")),
            )
        },
    }


def _checkpoint_chunk_inventory(
    checkpoints: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for document in checkpoints:
        for value in document.get("verified_iq_chunks", []):
            if not isinstance(value, dict) or "relative_path" not in value:
                raise ValueError("row checkpoint contains an invalid IQ chunk receipt")
            relative_path = str(value["relative_path"])
            receipt = dict(value)
            previous = inventory.setdefault(relative_path, receipt)
            if previous != receipt:
                raise ValueError(f"conflicting IQ chunk receipts: {relative_path}")
    return dict(sorted(inventory.items()))


def run_canary(
    *,
    frozen: FrozenInput,
    reader: FrozenCi16Reader,
    binding: AnalyzerBinding,
    output_root: Path,
    resume: bool,
    maximum_rows: int | None,
    continue_on_error: bool,
) -> dict[str, Any]:
    if maximum_rows is not None and maximum_rows < 1:
        raise ValueError("maximum rows must be positive")
    _validate_output_root(output_root, getattr(reader, "capture_root", None))
    rows = frozen.rows if maximum_rows is None else frozen.rows[:maximum_rows]
    output_root.mkdir(parents=True, exist_ok=True)
    checkpoint_documents: dict[str, dict[str, Any]] = {}
    for row in frozen.rows:
        path = checkpoint_path(output_root, row)
        identity = _checkpoint_identity(frozen, row, reader.manifest_digest, binding)
        if not path.is_file():
            continue
        try:
            existing = _json_object(path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid existing checkpoint requires review: {path}") from error
        if existing.get("identity") != identity:
            raise ValueError(f"checkpoint identity changed; use a new output root: {path}")
        if reusable_checkpoint(path, identity):
            if not resume and row in rows:
                raise ValueError(f"existing checkpoint requires --resume: {path}")
            checkpoint_documents[row.row_key] = existing
        elif not resume and row in rows:
            raise ValueError(f"non-reusable checkpoint requires --resume: {path}")
    reused = 0
    for position, row in enumerate(rows, start=1):
        path = checkpoint_path(output_root, row)
        identity = _checkpoint_identity(frozen, row, reader.manifest_digest, binding)
        if resume and reusable_checkpoint(path, identity):
            reused += 1
            print(f"row {position}/{len(rows)} reuse {row.row_key}", flush=True)
            continue
        print(f"row {position}/{len(rows)} analyze {row.row_key}", flush=True)
        try:
            document = analyze_row(frozen=frozen, row=row, reader=reader, binding=binding)
        except Exception as error:
            if not continue_on_error:
                raise
            document = _execution_error(
                frozen=frozen,
                row=row,
                reader=reader,
                binding=binding,
                error=error,
            )
        _atomic_json(path, document)
        checkpoint_documents[row.row_key] = document
        _atomic_json(
            output_root / "index.json",
            _index_document(
                frozen=frozen,
                reader=reader,
                binding=binding,
                checkpoints=tuple(checkpoint_documents.values()),
            ),
        )

    checkpoints = tuple(checkpoint_documents.values())
    cohorts = published_cohorts(frozen.rows)
    gates = evaluate_published_gates(frozen=frozen, cohorts=cohorts, checkpoints=checkpoints)
    index = _index_document(
        frozen=frozen,
        reader=reader,
        binding=binding,
        checkpoints=checkpoints,
    )
    _atomic_json(output_root / "index.json", index)
    document = {
        "schema": SCHEMA,
        "status": (
            "complete"
            if index["completed_row_count"] == len(frozen.rows)
            and index["execution_error_count"] == 0
            else "partial"
        ),
        "session_id": SESSION_ID,
        "run_id": RUN_ID,
        "frozen_input_sha256": frozen.digest,
        "recording_manifest_sha256": reader.manifest_digest,
        "harness_source_sha256": _file_digest(Path(__file__).resolve()),
        "analyzer": {
            "api": binding.api_name,
            "source_sha256": binding.source_sha256,
            "source_inventory": binding.source_inventory,
            "runtime_inventory": binding.runtime_inventory,
            "config_digest": binding.config_digest,
            "config": binding.config,
        },
        "population": {
            "row_count": len(frozen.rows),
            "cohort_counts": {name: len(keys) for name, keys in cohorts.items()},
            "cohort_row_key_digests": {
                name: _value_digest(list(keys)) for name, keys in cohorts.items()
            },
            "matched_alias_null_peer_method": (
                "one unique nearest-time same-scope V2/V3-no-result row per V3 loss; "
                "alias residual and row key are deterministic tie-breaks"
            ),
        },
        "published_gates": PUBLISHED_GATES,
        "gate_evaluation": gates,
        "index": index,
        "checkpoint_policy": {
            "row_atomic": True,
            "identity_bound_resume": True,
            "execution_errors_reusable": False,
        },
        "verified_consumed_chunks": _checkpoint_chunk_inventory(checkpoints),
        "scope": {
            "candidate_only": True,
            "standard_pipeline_modified": False,
            "new_rf_collected": False,
            "qnap_written": False,
            "acquisition_recovery_is_scientific_qualification": False,
        },
    }
    _atomic_json(output_root / "canary.json", document)
    print(f"reused {reused}/{len(rows)} scheduled row checkpoints", flush=True)
    return document


def main() -> None:
    arguments = _arguments()
    frozen = load_frozen_input(arguments.input)
    binding = load_v4_binding()
    reader = FrozenCi16Reader(
        arguments.capture_root,
        expected_manifest_digest=FROZEN_RECORDING_MANIFEST_SHA256,
        expected_session_id=SESSION_ID,
    )
    result = run_canary(
        frozen=frozen,
        reader=reader,
        binding=binding,
        output_root=arguments.output_root,
        resume=arguments.resume,
        maximum_rows=arguments.maximum_rows,
        continue_on_error=arguments.continue_on_error,
    )
    print(json.dumps(result["gate_evaluation"], indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
