#!/usr/bin/env python3
"""Run the focused 150802 alias-aware, two-receiver common-orbit audit.

This is a retrospective, report-only falsification experiment.  It binds one
replay-qualified absolute CFO lift on each receiver, selects one common TLE
identity and epoch using training rows only, gives each receiver its own affine
frequency nuisance, and evaluates the last 40% against degree-1/2/3 radio-only
polynomials.  The complete visible-catalogue search is repeated at forty
matched wrong times.

The receivers are two channels of the same Pluto and share a sample clock.
They are useful channel replicas, not independent instruments.  No result from
this tool is eligible to persist or promote a named transmitter identity.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from leo.contracts.sky import ObserverSiteV1
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import (
    MINIMUM_PLAUSIBLE_ALTITUDE_KM,
    parse_element_sets,
    propagate_grid,
)
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import observe_grid

try:
    from tools import report_five_dwell_tle_cone as cone
except ModuleNotFoundError:  # Direct ``python tools/...`` invocation.
    import report_five_dwell_tle_cone as cone


ROOT = Path(__file__).resolve().parents[1]
SESSION_ID = "cap-20260825T150802-473cb5bbcbd6"
RUN_ID = "capture-a5d45dd7752c4fc7833cd017a289f8d7"
CAPTURE_START_UTC_NS = 1_787_670_485_644_673_668
CAPTURE_DURATION_S = 60.0
STREAM_FIRST_SAMPLE_UTC_NS = 1_787_670_485_580_127_359
STREAM_PATH_OFFSET_S = (STREAM_FIRST_SAMPLE_UTC_NS - CAPTURE_START_UTC_NS) / 1_000_000_000
RF_FREQUENCY_HZ = 11_440_312_498.0
SAMPLE_RATE_HZ = 2_500_000
ALIAS_SPACING_HZ = SAMPLE_RATE_HZ / 11.0

RX1_SCOPE = "sha256:7f564aad7246e3f24930ae2851c7ddfd58cf0879a052cb5fc304b897e063c74f"
RX1_TRAJECTORY_ID = "sha256:92955a7dc86076490a7150b7f233ef64519fb7c0999bba1e62d94dfa531b5d8c"
RX1_BRANCH_ID = "sha256:f6d13ea406384f2a18d39063c7ee42fe8ee005e48bf058cc796065f89662a7da"
RX1_ALIAS_INDEX = 0
RX0_SCOPE = "sha256:f96018dcb38c192b83c28cc99040e43254a0b287d1c9a374dc5677736e49ee80"
RX0_TRAJECTORY_ID = "sha256:4bc2bfb418476bf2fc6365c3ec1eb18b78f2b8331af5b198ad5960389c3cc920"
RX0_BRANCH_ID = "sha256:d9fe5a2c5028f3d8f35d44f21e06ca88cd3af5d8818fc477eb96518823846470"
RX0_ALIAS_INDEX = 2

TRAIN_FRACTION = 0.60
BIN_WIDTH_S = 0.25
EPOCH_STEP_S = 0.05
ALLOWED_EPOCH_BOUNDS_S = (0.30, 2.0, 2.5)
DEFAULT_EPOCH_BOUND_S = 2.5
PRIMARY_DRIFT_BOUND_HZ_S = 200.0
DRIFT_SENSITIVITY_BOUNDS_HZ_S = (0.0, 25.0, 200.0)
MINIMUM_VISIBILITY_FRACTION = 0.95
POLYNOMIAL_DEGREES = (1, 2, 3)
WRONG_TIME_SHIFTS_S = tuple(float(value) for value in range(-600, 601, 30) if value)

MAXIMUM_HOLDOUT_RMS_HZ = 500.0
MINIMUM_POLYNOMIAL_ADVANTAGE_HZ = 100.0
MINIMUM_RUNNER_MARGIN_HZ = 100.0
MAXIMUM_WRONG_TIME_EMPIRICAL_P = 0.05
MINIMUM_REPLAY_MARGIN = 0.05

TLE_DIGEST = "sha256:9bb59fcf68fa36ce234ae9be79a492f0b92abc23bcf4f040bb5b64b61d3e31ad"
TLE_COLLECTED_UTC_NS = 1_787_666_532_658_586_719
DEFAULT_TLE_SNAPSHOT = Path(
    "/var/lib/leo/tle/archive/space-track/"
    "1787666532658586719-"
    "9bb59fcf68fa36ce234ae9be79a492f0b92abc23bcf4f040bb5b64b61d3e31ad.tle"
)

ANALYSIS_ROOT = (
    Path("/srv/bulk/leo/analysis") / SESSION_ID / RUN_ID / "scientific" / "path-standard"
)
RX1_ROOT = ANALYSIS_ROOT / RX1_SCOPE
RX0_ROOT = ANALYSIS_ROOT / RX0_SCOPE

DEFAULT_INPUT_PATHS = {
    "recording_manifest": Path("/srv/bulk/leo/recordings/2026/08/25")
    / SESSION_ID
    / "manifest.json",
    "direct_rows": ROOT
    / "reports/figures/2026_08_25_joint_cfo_delay_acceleration/joint-model-rows.jsonl",
    "joint_evidence": ROOT / "reports/figures/2026_08_25_joint_cfo_delay_acceleration/"
    "joint-cfo-delay-acceleration-evidence.json",
    "long_evidence": ROOT
    / "reports/figures/2026_08_25_counter_continuous_frame_timing/long-track-evidence.json",
    "frame_rows_gz": ROOT / "reports/figures/2026_08_25_counter_continuous_frame_timing/"
    "long-track-frame-rows.jsonl.gz",
    "rx1_final_bank": RX1_ROOT / "standard.final-trajectory-bank.v3.json",
    "rx1_replay": RX1_ROOT / "standard.cfo-lift-replay.v4.json",
    "rx0_alias_map": RX0_ROOT / "standard.cfo-alias-map.v2.json",
    "rx0_dealiased_bank": RX0_ROOT / "standard.dealiased-trajectory-bank.v4.json",
    "rx0_final_bank": RX0_ROOT / "standard.final-trajectory-bank.v3.json",
    "rx0_replay": RX0_ROOT / "standard.cfo-lift-replay.v4.json",
}

EXPECTED_INPUT_DIGESTS = {
    "recording_manifest": (
        "sha256:ab55917851a9cd37af94b6145cc719f7b8d9d0809f2202a2dcd1ac38c3e7a31e"
    ),
    "direct_rows": "sha256:05f33a0b492b84cda166bc7982c5554778c747f065ed93b4386eda60b3ff582c",
    "joint_evidence": "sha256:45d31ac36f71d45bb792c5dd4be84b36b71cee97865ed0c33b073f90e3f64208",
    "long_evidence": "sha256:619a715143c20801efbe8be3dee012b1a83e3fc730d588bb3a2c6cd2382de579",
    "frame_rows_gz": "sha256:38beb847c417e4b69f8c8ed64acda1d24116ad47531dc2ee3e601d61cd3bda0f",
    "rx1_final_bank": "sha256:720a3f740c4071de03c3710332dacf6780e904e44d7613135bfd3b3791de1bd2",
    "rx1_replay": "sha256:773a5e131552a0946702daf719da4400b89af6296356aa35146e2c59c2cc6d77",
    "rx0_alias_map": "sha256:e21104ff1a3dc172d0861a2aa0cb50dd4a59dea296ae380e352d34fb8ab465a8",
    "rx0_dealiased_bank": (
        "sha256:95350c2c6878fabe11fccc03e7017c97cd3beaa9807f581f9c86c52c76026e14"
    ),
    "rx0_final_bank": "sha256:1c1536cb7336779c1ba028609bd54afef962c5c5890267e69fca5af581e4fd0a",
    "rx0_replay": "sha256:4dafe3f8567a8a44d998257d1976253c8fa72fc5da7b73ec1b64061f8265a80b",
    "tle_snapshot": TLE_DIGEST,
}


@dataclass(frozen=True, slots=True)
class FrozenFile:
    label: str
    path: Path
    payload: bytes
    digest: str


@dataclass(frozen=True, slots=True)
class MemberSeries:
    label: str
    path: str
    source_kind: str
    rf_hz: float
    source_row_count: int
    time_s: np.ndarray
    cfo_hz: np.ndarray
    rows_per_bin: np.ndarray
    train: np.ndarray

    @property
    def train_count(self) -> int:
        return int(np.count_nonzero(self.train))

    @property
    def holdout_count(self) -> int:
        return int(np.count_nonzero(~self.train))


@dataclass(frozen=True, slots=True)
class PredictionField:
    shift_s: float
    time_s: np.ndarray
    doppler_hz: np.ndarray
    elevation_deg: np.ndarray
    metadata: tuple[dict[str, Any], ...]
    horizon_deg: float


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def freeze_file(label: str, path: Path, expected_digest: str | None = None) -> FrozenFile:
    resolved = path.resolve(strict=True)
    payload = resolved.read_bytes()
    digest = sha256_bytes(payload)
    if expected_digest is not None and digest != expected_digest:
        raise ValueError(f"{label} digest differs: expected {expected_digest}, observed {digest}")
    return FrozenFile(label, resolved, payload, digest)


def verify_frozen_files(snapshots: tuple[FrozenFile, ...]) -> None:
    for snapshot in snapshots:
        observed = sha256_bytes(snapshot.path.read_bytes())
        if observed != snapshot.digest:
            raise RuntimeError(f"startup-frozen file changed during execution: {snapshot.label}")


def json_document(snapshot: FrozenFile) -> dict[str, Any]:
    value = json.loads(snapshot.payload)
    if not isinstance(value, dict):
        raise ValueError(f"{snapshot.label} is not a JSON object")
    return value


def code_snapshots() -> tuple[FrozenFile, ...]:
    import leo.sky.doppler as doppler_module
    import leo.sky.propagation as propagation_module
    import leo.sky.sampling as sampling_module
    import leo.sky.screening as screening_module

    paths = {
        "experiment_tool": Path(__file__),
        "cone_tool": Path(cone.__file__),
        "doppler_core": Path(doppler_module.__file__),
        "propagation_core": Path(propagation_module.__file__),
        "sampling_core": Path(sampling_module.__file__),
        "screening_core": Path(screening_module.__file__),
    }
    return tuple(freeze_file(label, path) for label, path in paths.items())


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--tle-snapshot", type=Path, default=DEFAULT_TLE_SNAPSHOT)
    parser.add_argument(
        "--epoch-bound-s",
        type=float,
        choices=ALLOWED_EPOCH_BOUNDS_S,
        default=DEFAULT_EPOCH_BOUND_S,
    )
    parser.add_argument("--horizon-deg", type=float, default=cone.DEFAULT_HORIZON_DEG)
    parser.add_argument(
        "--validate-inputs-only",
        action="store_true",
        help="freeze and validate exact inputs without propagating any TLE field",
    )
    for label, default in DEFAULT_INPUT_PATHS.items():
        parser.add_argument(f"--{label.replace('_', '-')}", type=Path, default=default)
    return parser.parse_args()


def _input_paths(args: argparse.Namespace) -> dict[str, Path]:
    paths = {label: Path(getattr(args, label)) for label in DEFAULT_INPUT_PATHS}
    paths["tle_snapshot"] = Path(args.tle_snapshot)
    return paths


def freeze_inputs(args: argparse.Namespace) -> dict[str, FrozenFile]:
    return {
        label: freeze_file(label, path, EXPECTED_INPUT_DIGESTS[label])
        for label, path in _input_paths(args).items()
    }


def _strict_replay_pass(row: dict[str, Any]) -> bool:
    return bool(
        row.get("geometry_display_eligible")
        and float(row.get("duration_s", 0.0)) >= 1.0
        and int(row.get("observation_count", 0)) >= 5
        and int(row.get("evaluated_probe_count", 0)) >= 20
        and float(row.get("block_coverage_ratio", 0.0)) >= 0.5
        and float(row.get("median_block_corrected_margin", -math.inf)) >= MINIMUM_REPLAY_MARGIN
        and int(row.get("harmful_block_count", -1)) == 0
        and int(row.get("maximum_consecutive_harmful_blocks", -1)) == 0
        and float(row.get("residual_rms_hz", math.inf)) <= 2_500.0
        and float(row.get("residual_max_hz", math.inf)) <= 8_000.0
    )


def validate_unique_alias(
    final_bank: dict[str, Any],
    replay: dict[str, Any],
    *,
    trajectory_id: str,
    branch_id: str,
    alias_index: int,
) -> dict[str, Any]:
    if final_bank.get("lift_replay_digest") != replay.get("content_digest"):
        raise ValueError("final bank is not bound to the supplied replay product")
    trajectories = [
        row
        for row in final_bank.get("trajectories", ())
        if row.get("trajectory_id") == trajectory_id
    ]
    if len(trajectories) != 1:
        raise ValueError(f"expected exactly one final trajectory {trajectory_id}")
    trajectory = trajectories[0]
    if (
        trajectory.get("branch_id") != branch_id
        or int(trajectory.get("alias_index")) != alias_index
    ):
        raise ValueError("final trajectory branch or alias differs from the frozen selection")
    branch_rows = [row for row in replay.get("rows", ()) if row.get("branch_id") == branch_id]
    strict = [row for row in branch_rows if _strict_replay_pass(row)]
    if len(strict) != 1 or int(strict[0].get("alias_index")) != alias_index:
        aliases = [int(row.get("alias_index")) for row in strict]
        raise ValueError(f"strict replay gate did not yield unique alias {alias_index}: {aliases}")
    selected = strict[0]
    for key in (
        "evaluated_probe_count",
        "evaluated_block_count",
        "harmful_block_count",
        "maximum_consecutive_harmful_blocks",
    ):
        if int(trajectory.get(key)) != int(selected.get(key)):
            raise ValueError(f"final/replay {key} differs")
    for key in ("block_coverage_ratio", "median_block_corrected_margin"):
        if not math.isclose(float(trajectory.get(key)), float(selected.get(key)), abs_tol=1e-12):
            raise ValueError(f"final/replay {key} differs")
    return {
        "trajectory_id": trajectory_id,
        "branch_id": branch_id,
        "alias_index": alias_index,
        "unique_strict_replay_winner": True,
        "strict_gate": {
            "minimum_median_corrected_margin": MINIMUM_REPLAY_MARGIN,
            "zero_harmful_blocks": True,
            "minimum_block_coverage_ratio": 0.5,
            "minimum_probe_count": 20,
            "maximum_residual_rms_hz": 2_500.0,
            "maximum_residual_hz": 8_000.0,
        },
        "selected_replay": {
            key: selected.get(key)
            for key in (
                "duration_s",
                "observation_count",
                "evaluated_probe_count",
                "evaluated_block_count",
                "block_coverage_ratio",
                "median_block_corrected_margin",
                "q10_block_margin_delta",
                "harmful_block_count",
                "maximum_consecutive_harmful_blocks",
                "residual_rms_hz",
                "residual_max_hz",
            )
        },
        "rejected_same_branch_lifts": [
            {
                "alias_index": int(row["alias_index"]),
                "median_block_corrected_margin": row.get("median_block_corrected_margin"),
                "harmful_block_count": row.get("harmful_block_count"),
            }
            for row in branch_rows
            if row is not selected
        ],
        "trajectory": trajectory,
    }


def _parse_jsonl(snapshot: FrozenFile) -> list[dict[str, Any]]:
    rows = []
    for index, line in enumerate(snapshot.payload.splitlines(), start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{snapshot.label} line {index} is invalid JSON") from error
        if not isinstance(value, dict):
            raise ValueError(f"{snapshot.label} line {index} is not an object")
        rows.append(value)
    return rows


def median_bins(
    times_s: np.ndarray, values_hz: np.ndarray, width_s: float = BIN_WIDTH_S
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    times = np.asarray(times_s, dtype=np.float64)
    values = np.asarray(values_hz, dtype=np.float64)
    if times.ndim != 1 or values.shape != times.shape or times.size == 0:
        raise ValueError("binning requires equally sized nonempty one-dimensional arrays")
    if not np.all(np.isfinite(times)) or not np.all(np.isfinite(values)) or width_s <= 0.0:
        raise ValueError("binning inputs must be finite and width must be positive")
    indexes = np.floor(times / width_s + 1e-12).astype(np.int64)
    rows = []
    for index in np.unique(indexes):
        selected = indexes == index
        rows.append(
            (
                float(np.median(times[selected])),
                float(np.median(values[selected])),
                int(np.count_nonzero(selected)),
            )
        )
    return (
        np.asarray([row[0] for row in rows], dtype=np.float64),
        np.asarray([row[1] for row in rows], dtype=np.float64),
        np.asarray([row[2] for row in rows], dtype=np.int64),
    )


def _member(
    *,
    label: str,
    path: str,
    source_kind: str,
    raw_times_s: np.ndarray,
    raw_cfo_hz: np.ndarray,
    train_cutoff_local_s: float,
) -> MemberSeries:
    raw_times = np.asarray(raw_times_s, dtype=np.float64)
    raw_cfo = np.asarray(raw_cfo_hz, dtype=np.float64)
    raw_train = raw_times < train_cutoff_local_s
    train_times, train_cfo, train_counts = median_bins(raw_times[raw_train], raw_cfo[raw_train])
    holdout_times, holdout_cfo, holdout_counts = median_bins(
        raw_times[~raw_train], raw_cfo[~raw_train]
    )
    local_times = np.concatenate((train_times, holdout_times))
    cfo = np.concatenate((train_cfo, holdout_cfo))
    counts = np.concatenate((train_counts, holdout_counts))
    times = local_times + STREAM_PATH_OFFSET_S
    train_cutoff_s = train_cutoff_local_s + STREAM_PATH_OFFSET_S
    train = times < train_cutoff_s
    if np.count_nonzero(train) != train_times.size:
        raise ValueError(f"{label}: a median bin crossed the shared UTC cutoff")
    if np.count_nonzero(train) < max(POLYNOMIAL_DEGREES) + 1:
        raise ValueError(f"{label} has too few training bins for the cubic null")
    if np.count_nonzero(~train) < 3:
        raise ValueError(f"{label} has too few holdout bins")
    return MemberSeries(
        label,
        path,
        source_kind,
        RF_FREQUENCY_HZ,
        int(np.asarray(raw_times_s).size),
        times,
        cfo,
        counts,
        train,
    )


def _counter_gate(document: dict[str, Any]) -> dict[str, Any]:
    counter = document.get("counter_continuity")
    if not isinstance(counter, dict):
        raise ValueError("long evidence lacks counter continuity")
    required_zero = (
        "gap_count",
        "missing_sample_count",
        "overflow_count",
        "enqueue_failure_count",
        "terminal_rejected_gap_count",
        "terminal_rejected_missing_sample_count",
        "terminal_rejected_overflow_count",
    )
    passed = bool(
        counter.get("sample_loss_observable")
        and int(counter.get("segment_count", 0)) == 1
        and all(int(counter.get(key, -1)) == 0 for key in required_zero)
    )
    if not passed:
        raise ValueError("RX1 counter-continuity prerequisite failed")
    return {"passed": True, **{key: counter.get(key) for key in required_zero}}


def load_and_validate_members(
    frozen: dict[str, FrozenFile],
) -> tuple[tuple[MemberSeries, MemberSeries], dict[str, Any]]:
    recording = json_document(frozen["recording_manifest"])
    joint = json_document(frozen["joint_evidence"])
    long = json_document(frozen["long_evidence"])
    rx1_final = json_document(frozen["rx1_final_bank"])
    rx1_replay = json_document(frozen["rx1_replay"])
    rx0_alias = json_document(frozen["rx0_alias_map"])
    rx0_dealiased = json_document(frozen["rx0_dealiased_bank"])
    rx0_final = json_document(frozen["rx0_final_bank"])
    rx0_replay = json_document(frozen["rx0_replay"])

    rx1_gate = validate_unique_alias(
        rx1_final,
        rx1_replay,
        trajectory_id=RX1_TRAJECTORY_ID,
        branch_id=RX1_BRANCH_ID,
        alias_index=RX1_ALIAS_INDEX,
    )
    rx0_gate = validate_unique_alias(
        rx0_final,
        rx0_replay,
        trajectory_id=RX0_TRAJECTORY_ID,
        branch_id=RX0_BRANCH_ID,
        alias_index=RX0_ALIAS_INDEX,
    )
    rx1_trajectory = rx1_gate.pop("trajectory")
    rx0_trajectory = rx0_gate.pop("trajectory")

    streams = [row for row in recording.get("streams", ()) if row.get("stream_id") == "stream-1"]
    if len(streams) != 1:
        raise ValueError("recording manifest does not contain exactly one stream-1")
    stream = streams[0]
    first_sample_ns = int(
        stream.get("timing", {}).get("first_sample", {}).get("estimate_utc_ns", -1)
    )
    settings = stream.get("applied_settings", {})
    if first_sample_ns != STREAM_FIRST_SAMPLE_UTC_NS:
        raise ValueError("stream-1 first-sample estimate differs from the frozen UTC anchor")
    if int(settings.get("sample_rate_hz", -1)) != SAMPLE_RATE_HZ:
        raise ValueError("stream-1 sample rate differs")
    if int(settings.get("center_frequency_hz", -1)) + 9_750_000_000 != int(RF_FREQUENCY_HZ):
        raise ValueError("stream-1 applied IF plus documented LNB LO differs from RF")

    if joint.get("input", {}).get("trajectory_id") != RX1_TRAJECTORY_ID:
        raise ValueError("joint evidence is not bound to the RX1 trajectory")
    if int(joint.get("input", {}).get("detection_count", -1)) != 550:
        raise ValueError("joint evidence does not declare exactly 550 direct CFO rows")
    if joint.get("input", {}).get("trajectory_bank_sha256") != EXPECTED_INPUT_DIGESTS[
        "rx1_final_bank"
    ].removeprefix("sha256:"):
        raise ValueError("joint evidence final-bank binding differs")
    if long.get("trajectory", {}).get("trajectory_id") != RX1_TRAJECTORY_ID:
        raise ValueError("long continuity evidence is not bound to the RX1 trajectory")
    if joint.get("input", {}).get("long_evidence_sha256") != frozen[
        "long_evidence"
    ].digest.removeprefix("sha256:"):
        raise ValueError("joint evidence long-evidence digest differs")
    decompressed_frame_digest = sha256_bytes(gzip.decompress(frozen["frame_rows_gz"].payload))
    declared_frame_digest = "sha256:" + str(long.get("artifacts", {}).get("frame_rows_sha256"))
    if decompressed_frame_digest != declared_frame_digest:
        raise ValueError("committed frame rows do not match long-evidence uncompressed digest")
    counter_gate = _counter_gate(long)

    direct_rows = _parse_jsonl(frozen["direct_rows"])
    if len(direct_rows) != 550:
        raise ValueError("direct CFO input must contain exactly 550 rows")
    rx1_all_time = np.asarray([row["cfo_measurement_time_s"] for row in direct_rows], dtype=float)
    rx1_all_cfo = np.asarray([row["tracking_cfo_hz"] for row in direct_rows], dtype=float)
    if not np.all(np.diff(rx1_all_time) > 0.0):
        raise ValueError("direct CFO measurement times are not strictly increasing")
    if float(np.min([row["margin"] for row in direct_rows])) < 0.0:
        raise ValueError("direct CFO rows include a nonpositive selected margin")
    if rx1_all_time[0] < float(rx1_trajectory["start_s"]) or rx1_all_time[-1] > float(
        rx1_trajectory["end_s"]
    ):
        raise ValueError("direct CFO rows leave the selected RX1 trajectory")

    numerator = int(rx0_alias.get("alias_spacing_numerator_hz", -1))
    denominator = int(rx0_alias.get("alias_spacing_denominator", -1))
    if (numerator, denominator) != (SAMPLE_RATE_HZ, 11):
        raise ValueError("RX0 alias spacing differs from 2.5 MHz / 11")
    if rx0_final.get("dealiased_bank_digest") != rx0_dealiased.get("content_digest"):
        raise ValueError("RX0 final bank is not bound to the dealiased bank")
    wanted = set(rx0_trajectory.get("observation_ids", ()))
    by_id = {
        row["observation_id"]: row
        for row in rx0_dealiased.get("observations", ())
        if row.get("observation_id") in wanted
    }
    if set(by_id) != wanted or len(wanted) != 67:
        raise ValueError("RX0 selected trajectory does not resolve to exactly 67 observations")
    ordered = sorted(by_id.values(), key=lambda row: (float(row["time_s"]), row["observation_id"]))
    rx0_time = np.asarray([row["time_s"] for row in ordered], dtype=float)
    # Deliberately never consume raw_cfo_hz: it mixes observed +1/+2 aliases.
    rx0_cfo = np.asarray(
        [float(row["component_cfo_hz"]) + RX0_ALIAS_INDEX * ALIAS_SPACING_HZ for row in ordered],
        dtype=float,
    )
    canonical = np.asarray(rx0_trajectory["canonical_coefficients_hz"], dtype=float)
    absolute = np.asarray(rx0_trajectory["absolute_coefficients_hz"], dtype=float)
    if not math.isclose(
        float(absolute[-1] - canonical[-1]),
        RX0_ALIAS_INDEX * ALIAS_SPACING_HZ,
        abs_tol=1e-8,
    ):
        raise ValueError("RX0 final trajectory lift is not the frozen +2 alias")

    common_start_local_s = max(float(rx1_trajectory["start_s"]), float(rx0_trajectory["start_s"]))
    common_end_local_s = min(float(rx1_trajectory["end_s"]), float(rx0_trajectory["end_s"]))
    if common_end_local_s <= common_start_local_s:
        raise ValueError("receiver trajectories do not have a common local-time interval")
    train_cutoff_local_s = common_start_local_s + TRAIN_FRACTION * (
        common_end_local_s - common_start_local_s
    )
    rx1_common = (rx1_all_time >= common_start_local_s) & (rx1_all_time <= common_end_local_s)
    rx1_time = rx1_all_time[rx1_common]
    rx1_cfo = rx1_all_cfo[rx1_common]
    rx1 = _member(
        label="RX1-direct",
        path="stream-1/RX1",
        source_kind="common-overlap subset of 550 trajectory-conditioned direct GLRT CFO centroids",
        raw_times_s=rx1_time,
        raw_cfo_hz=rx1_cfo,
        train_cutoff_local_s=train_cutoff_local_s,
    )
    rx0 = _member(
        label="RX0-canonical",
        path="stream-1/RX0",
        source_kind="67 canonical dealiased observations lifted by fixed alias +2",
        raw_times_s=rx0_time,
        raw_cfo_hz=rx0_cfo,
        train_cutoff_local_s=train_cutoff_local_s,
    )
    overlap_start = max(float(rx1.time_s.min()), float(rx0.time_s.min()))
    overlap_end = min(float(rx1.time_s.max()), float(rx0.time_s.max()))
    if overlap_end <= overlap_start:
        raise ValueError("receiver trajectories do not overlap")
    gates = {
        "rx1_alias": rx1_gate,
        "rx0_alias": rx0_gate,
        "rx1_counter_continuity": counter_gate,
        "fixed_alias_construction": (
            "RX0 cfo = component_cfo_hz + 2*(2_500_000/11); raw_cfo_hz is forbidden. "
            "The constant alias lift is algebraically absorbed by the separate RX0 "
            "intercept, so it cannot affect common-orbit residuals or ranking and serves "
            "only as an upstream strict-replay prerequisite."
        ),
        "time_authority": {
            "nominal_dwell_start_utc_ns": CAPTURE_START_UTC_NS,
            "stream_first_sample_estimate_utc_ns": STREAM_FIRST_SAMPLE_UTC_NS,
            "stream_path_offset_s": STREAM_PATH_OFFSET_S,
            "conversion": ("dwell_relative_time_s = stream_local_time_s + stream_path_offset_s"),
            "recording_manifest_digest": frozen["recording_manifest"].digest,
        },
        "common_overlap_split": {
            "common_start_local_s": common_start_local_s,
            "common_end_local_s": common_end_local_s,
            "common_duration_s": common_end_local_s - common_start_local_s,
            "train_fraction": TRAIN_FRACTION,
            "train_cutoff_local_s": train_cutoff_local_s,
            "train_cutoff_dwell_s": train_cutoff_local_s + STREAM_PATH_OFFSET_S,
            "derivation": "common_start + 0.60*(common_end-common_start)",
            "rx1_available_direct_row_count": 550,
            "rx1_common_overlap_raw_row_count": int(rx1_time.size),
            "rx0_common_overlap_raw_row_count": int(rx0_time.size),
        },
        "train_cutoff_s": train_cutoff_local_s + STREAM_PATH_OFFSET_S,
        "bin_width_s": BIN_WIDTH_S,
        "overlap": {
            "start_s": overlap_start,
            "end_s": overlap_end,
            "duration_s": overlap_end - overlap_start,
            "holdout_overlap_duration_s": max(
                0.0, overlap_end - (train_cutoff_local_s + STREAM_PATH_OFFSET_S)
            ),
        },
        "members": [member_evidence(item) for item in (rx1, rx0)],
    }
    return (rx1, rx0), gates


def member_evidence(member: MemberSeries) -> dict[str, Any]:
    return {
        "label": member.label,
        "path": member.path,
        "source_kind": member.source_kind,
        "rf_hz": member.rf_hz,
        "source_row_count": member.source_row_count,
        "analysis_bin_count": int(member.time_s.size),
        "train_bin_count": member.train_count,
        "holdout_bin_count": member.holdout_count,
        "time_start_s": float(member.time_s.min()),
        "time_end_s": float(member.time_s.max()),
        "minimum_rows_per_bin": int(member.rows_per_bin.min()),
        "median_rows_per_bin": float(np.median(member.rows_per_bin)),
        "maximum_rows_per_bin": int(member.rows_per_bin.max()),
    }


def polynomial_null(member: MemberSeries) -> dict[str, Any]:
    reference = float(np.mean(member.time_s[member.train]))
    scale = float(np.max(np.abs(member.time_s[member.train] - reference)))
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError(f"{member.label}: invalid polynomial time scale")
    normalized = (member.time_s - reference) / scale
    models = []
    for degree in POLYNOMIAL_DEGREES:
        design = np.vander(normalized, N=degree + 1, increasing=True)
        coefficients, *_ = np.linalg.lstsq(
            design[member.train], member.cfo_hz[member.train], rcond=None
        )
        residual = member.cfo_hz - design @ coefficients
        models.append(
            {
                "degree": degree,
                "reference_s": reference,
                "scale_s": scale,
                "normalized_coefficients_hz": coefficients.tolist(),
                "train_residual_rms_hz": rms(residual[member.train]),
                "holdout_residual_rms_hz": rms(residual[~member.train]),
            }
        )
    best = min(models, key=lambda row: (row["holdout_residual_rms_hz"], row["degree"]))
    return {
        "models": models,
        "holdout_oracle_best_degree": int(best["degree"]),
        "holdout_oracle_best_rms_hz": float(best["holdout_residual_rms_hz"]),
        "selection_role": "falsifier only; the holdout-oracle degree never selects TLE identity",
    }


def shared_curvature_null(
    members: tuple[MemberSeries, ...],
) -> dict[str, Any]:
    """Fit common quadratic/cubic curvature with separate member affine terms."""

    train_times = np.concatenate([member.time_s[member.train] for member in members])
    reference = float(np.mean(train_times))
    scale = float(np.max(np.abs(train_times - reference)))
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError("shared-curvature null has invalid training time scale")
    models = []
    for degree in POLYNOMIAL_DEGREES:
        designs = []
        values = []
        trains = []
        member_slices = []
        start = 0
        for member_index, member in enumerate(members):
            normalized = (member.time_s - reference) / scale
            design = np.zeros((member.time_s.size, 2 * len(members) + max(0, degree - 1)))
            design[:, 2 * member_index] = 1.0
            design[:, 2 * member_index + 1] = normalized
            for power in range(2, degree + 1):
                design[:, 2 * len(members) + power - 2] = normalized**power
            designs.append(design)
            values.append(member.cfo_hz)
            trains.append(member.train)
            member_slices.append(slice(start, start + member.time_s.size))
            start += member.time_s.size
        full_design = np.vstack(designs)
        full_values = np.concatenate(values)
        full_train = np.concatenate(trains)
        coefficients, *_ = np.linalg.lstsq(
            full_design[full_train], full_values[full_train], rcond=None
        )
        residual = full_values - full_design @ coefficients
        member_rows = []
        for member, selected in zip(members, member_slices, strict=True):
            member_residual = residual[selected]
            member_rows.append(
                {
                    "label": member.label,
                    "train_residual_rms_hz": rms(member_residual[member.train]),
                    "holdout_residual_rms_hz": rms(member_residual[~member.train]),
                }
            )
        models.append(
            {
                "degree": degree,
                "reference_s": reference,
                "scale_s": scale,
                "coefficients_hz": coefficients.tolist(),
                "member_fits": member_rows,
                "train_residual_rms_hz": aggregate_member_rms(
                    [row["train_residual_rms_hz"] for row in member_rows]
                ),
                "holdout_residual_rms_hz": aggregate_member_rms(
                    [row["holdout_residual_rms_hz"] for row in member_rows]
                ),
            }
        )
    best = min(models, key=lambda row: (row["holdout_residual_rms_hz"], row["degree"]))
    return {
        "models": models,
        "holdout_oracle_best_degree": int(best["degree"]),
        "holdout_oracle_best_rms_hz": float(best["holdout_residual_rms_hz"]),
        "selection_role": (
            "radio-only structural falsifier; common nonlinear curvature and separate "
            "member affine terms are fit on training, with degree chosen only for audit"
        ),
    }


def rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.asarray(values, dtype=np.float64) ** 2)))


def aggregate_member_rms(member_rms: list[float]) -> float:
    if not member_rms:
        raise ValueError("aggregate RMS requires at least one member")
    return float(math.sqrt(np.mean(np.square(np.asarray(member_rms, dtype=float)))))


def epoch_grid(epoch_bound_s: float) -> np.ndarray:
    if not any(
        math.isclose(epoch_bound_s, value, abs_tol=1e-12) for value in ALLOWED_EPOCH_BOUNDS_S
    ):
        raise ValueError("epoch bound must be 0.30, 2.0, or 2.5 seconds")
    steps = round(epoch_bound_s / EPOCH_STEP_S)
    return EPOCH_STEP_S * np.arange(-steps, steps + 1, dtype=np.float64)


def _uniform_grid(start_ns: int, end_ns: int, spacing_s: float = 0.25) -> SamplingGrid:
    step_ns = round(spacing_s * 1_000_000_000)
    count = max(3, math.ceil((end_ns - start_ns) / step_ns) + 1)
    instants = tuple(start_ns + index * step_ns for index in range(count))
    return SamplingGrid(instants, count // 2, spacing_s)


def prediction_field(
    catalogue: Any,
    observer: ObserverSiteV1,
    *,
    field_shift_s: float,
    epoch_bound_s: float,
    horizon_deg: float,
) -> PredictionField:
    field_start_ns = CAPTURE_START_UTC_NS + round(field_shift_s * 1_000_000_000)
    padding_s = epoch_bound_s + 0.5
    grid = _uniform_grid(
        field_start_ns - round(padding_s * 1_000_000_000),
        field_start_ns + round((CAPTURE_DURATION_S + padding_s) * 1_000_000_000),
    )
    propagated = propagate_grid(catalogue, grid)
    observed = observe_grid(propagated, observer, grid)
    times_s = (np.asarray(grid.utc_ns, dtype=np.float64) - field_start_ns) / 1_000_000_000
    core = (times_s >= 0.0) & (times_s <= CAPTURE_DURATION_S)
    plausible = observed.altitude_km[:, core].min(axis=1) > MINIMUM_PLAUSIBLE_ALTITUDE_KM
    selected = np.flatnonzero(
        observed.usable & plausible & (observed.elevation_deg[:, core].max(axis=1) >= horizon_deg)
    )
    if selected.size < 2:
        raise ValueError(f"field {field_shift_s:+g}s has fewer than two visible candidates")
    epochs = catalogue.element_epoch_utc_ns()
    metadata = tuple(
        {
            "catalogue_index": int(index),
            "catalog_number": int(catalogue.satellite_numbers[index]),
            "object_name": str(catalogue.names[index])[:64],
            "element_epoch_utc_ns": int(epochs[index]),
            "element_age_s": abs(field_start_ns - int(epochs[index])) / 1_000_000_000,
            "peak_elevation_deg": float(observed.elevation_deg[index, core].max()),
        }
        for index in selected
    )
    return PredictionField(
        field_shift_s,
        times_s,
        doppler_shift_hz(RF_FREQUENCY_HZ, observed.range_rate_km_s[selected]),
        observed.elevation_deg[selected],
        metadata,
        horizon_deg,
    )


def _member_epoch_metrics(
    member: MemberSeries,
    prediction_times_s: np.ndarray,
    prediction_hz: np.ndarray,
    shifts_s: np.ndarray,
    drift_bound_hz_s: float,
) -> dict[str, np.ndarray]:
    shifted = member.time_s[:, None] + shifts_s[None, :]
    prediction = np.interp(shifted.ravel(), prediction_times_s, prediction_hz).reshape(
        member.time_s.size, shifts_s.size
    )
    target = member.cfo_hz[:, None] - prediction
    reference = float(np.mean(member.time_s[member.train]))
    centered = member.time_s - reference
    denominator = float(np.sum(centered[member.train] ** 2))
    if denominator <= 0.0:
        raise ValueError(f"{member.label}: nuisance slope has zero training support")
    slopes = np.sum(centered[member.train, None] * target[member.train], axis=0) / denominator
    slopes = np.clip(slopes, -drift_bound_hz_s, drift_bound_hz_s)
    offsets = np.mean(target[member.train] - centered[member.train, None] * slopes[None, :], axis=0)
    residual = target - offsets[None, :] - centered[:, None] * slopes[None, :]
    return {
        "reference_s": np.full(shifts_s.size, reference),
        "offset_hz": offsets,
        "drift_hz_s": slopes,
        "train_rms_hz": np.sqrt(np.mean(residual[member.train] ** 2, axis=0)),
        "holdout_rms_hz": np.sqrt(np.mean(residual[~member.train] ** 2, axis=0)),
    }


def select_common_candidate(
    members: tuple[MemberSeries, ...],
    field: PredictionField,
    *,
    epoch_bound_s: float,
    drift_bound_hz_s: float,
    retain_top: int = 10,
) -> dict[str, Any]:
    shifts = epoch_grid(epoch_bound_s)
    candidates = []
    for satellite_index, metadata in enumerate(field.metadata):
        train_visibility_by_member = []
        holdout_visibility_by_member = []
        full_visibility_by_member = []
        for member in members:
            shifted = member.time_s[:, None] + shifts[None, :]
            elevations = np.interp(
                shifted.ravel(), field.time_s, field.elevation_deg[satellite_index]
            ).reshape(member.time_s.size, shifts.size)
            visible = elevations >= field.horizon_deg
            train_visibility_by_member.append(np.mean(visible[member.train], axis=0))
            holdout_visibility_by_member.append(np.mean(visible[~member.train], axis=0))
            full_visibility_by_member.append(np.mean(visible, axis=0))
        # Candidate and common-epoch eligibility are training-only. Holdout and
        # full-span visibility remain prospective falsifiers.
        valid_epochs = np.all(
            np.vstack(
                [values >= MINIMUM_VISIBILITY_FRACTION for values in train_visibility_by_member]
            ),
            axis=0,
        )
        if not np.any(valid_epochs):
            continue
        metrics = [
            _member_epoch_metrics(
                member,
                field.time_s,
                field.doppler_hz[satellite_index],
                shifts,
                drift_bound_hz_s,
            )
            for member in members
        ]
        train = np.sqrt(np.mean(np.vstack([row["train_rms_hz"] ** 2 for row in metrics]), axis=0))
        holdout = np.sqrt(
            np.mean(np.vstack([row["holdout_rms_hz"] ** 2 for row in metrics]), axis=0)
        )
        train = np.where(valid_epochs, train, math.inf)
        holdout = np.where(valid_epochs, holdout, math.inf)
        best_index = min(
            range(shifts.size),
            key=lambda index: (train[index], abs(shifts[index]), shifts[index]),
        )
        candidates.append(
            {
                **metadata,
                "epoch_adjustment_s": float(shifts[best_index]),
                "train_residual_rms_hz": float(train[best_index]),
                "holdout_residual_rms_hz": float(holdout[best_index]),
                "train_visibility_fraction_by_member": [
                    float(values[best_index]) for values in train_visibility_by_member
                ],
                "holdout_visibility_fraction_by_member": [
                    float(values[best_index]) for values in holdout_visibility_by_member
                ],
                "full_visibility_fraction_by_member": [
                    float(values[best_index]) for values in full_visibility_by_member
                ],
                "train_visibility_eligible": bool(
                    all(
                        values[best_index] >= MINIMUM_VISIBILITY_FRACTION
                        for values in train_visibility_by_member
                    )
                ),
                "holdout_visibility_eligible": bool(
                    all(
                        values[best_index] >= MINIMUM_VISIBILITY_FRACTION
                        for values in holdout_visibility_by_member
                    )
                ),
                "full_visibility_eligible": bool(
                    all(
                        values[best_index] >= MINIMUM_VISIBILITY_FRACTION
                        for values in full_visibility_by_member
                    )
                ),
                "member_fits": [
                    {
                        "label": member.label,
                        "nuisance_reference_s": float(metric["reference_s"][best_index]),
                        "fitted_frequency_offset_hz": float(metric["offset_hz"][best_index]),
                        "nuisance_drift_hz_s": float(metric["drift_hz_s"][best_index]),
                        "train_residual_rms_hz": float(metric["train_rms_hz"][best_index]),
                        "holdout_residual_rms_hz": float(metric["holdout_rms_hz"][best_index]),
                    }
                    for member, metric in zip(members, metrics, strict=True)
                ],
            }
        )
    if len(candidates) < 2:
        raise ValueError(f"field {field.shift_s:+g}s produced fewer than two eligible candidates")
    ranked = sorted(
        candidates,
        key=lambda row: (row["train_residual_rms_hz"], row["catalog_number"]),
    )
    return {
        "candidate_count": len(ranked),
        "best": ranked[0],
        "runner": ranked[1],
        "best_alternative_holdout_rms_hz": min(
            float(row["holdout_residual_rms_hz"]) for row in ranked[1:]
        ),
        "top_candidates": ranked[:retain_top],
    }


def _log_mse_gain(baseline_rms_hz: float, model_rms_hz: float) -> float:
    tiny = np.finfo(np.float64).tiny
    return float(2.0 * (math.log(max(baseline_rms_hz, tiny)) - math.log(max(model_rms_hz, tiny))))


def finish_field(
    selected: dict[str, Any],
    members: tuple[MemberSeries, ...],
    polynomials: tuple[dict[str, Any], ...],
    structural_null: dict[str, Any],
    epoch_bound_s: float,
) -> dict[str, Any]:
    best = selected["best"]
    runner = selected["runner"]
    member_orbit = [float(row["holdout_residual_rms_hz"]) for row in best["member_fits"]]
    member_polynomial = [float(row["holdout_oracle_best_rms_hz"]) for row in polynomials]
    aggregate_polynomial = aggregate_member_rms(member_polynomial)
    structural_rms = float(structural_null["holdout_oracle_best_rms_hz"])
    strongest_radio_null = min(aggregate_polynomial, structural_rms)
    aggregate_orbit = float(best["holdout_residual_rms_hz"])
    member_gains = [
        _log_mse_gain(polynomial, orbit)
        for polynomial, orbit in zip(member_polynomial, member_orbit, strict=True)
    ]
    runner_margin = float(runner["train_residual_rms_hz"] - best["train_residual_rms_hz"])
    alternative_holdout = float(selected["best_alternative_holdout_rms_hz"])
    alternative_margin = alternative_holdout - aggregate_orbit
    epoch_interior = bool(
        abs(float(best["epoch_adjustment_s"])) < epoch_bound_s - EPOCH_STEP_S / 2.0
    )
    selected_candidate_visibility_confirmed = bool(
        best["train_visibility_eligible"]
        and best["holdout_visibility_eligible"]
        and best["full_visibility_eligible"]
    )
    statistic = min(
        min(member_gains),
        _log_mse_gain(float(runner["train_residual_rms_hz"]), float(best["train_residual_rms_hz"])),
        _log_mse_gain(alternative_holdout, aggregate_orbit),
    )
    if not epoch_interior:
        statistic = min(statistic, -1.0)
    if not selected_candidate_visibility_confirmed:
        statistic = min(statistic, -1.0)
    return {
        "candidate_count": int(selected["candidate_count"]),
        "candidate_name": best["object_name"],
        "catalog_number": int(best["catalog_number"]),
        "epoch_adjustment_s": float(best["epoch_adjustment_s"]),
        "epoch_interior": epoch_interior,
        "train_visibility_fraction_by_member": best["train_visibility_fraction_by_member"],
        "holdout_visibility_fraction_by_member": best["holdout_visibility_fraction_by_member"],
        "full_visibility_fraction_by_member": best["full_visibility_fraction_by_member"],
        "train_visibility_eligible": bool(best["train_visibility_eligible"]),
        "holdout_visibility_eligible": bool(best["holdout_visibility_eligible"]),
        "full_visibility_eligible": bool(best["full_visibility_eligible"]),
        "selected_candidate_visibility_confirmed": selected_candidate_visibility_confirmed,
        "train_rms_hz": float(best["train_residual_rms_hz"]),
        "holdout_rms_hz": aggregate_orbit,
        "runner_name": runner["object_name"],
        "runner_catalog_number": int(runner["catalog_number"]),
        "runner_margin_hz": runner_margin,
        "best_alternative_holdout_rms_hz": alternative_holdout,
        "heldout_alternative_margin_hz": alternative_margin,
        "aggregate_best_per_member_polynomial_holdout_rms_hz": aggregate_polynomial,
        "shared_curvature_null": structural_null,
        "strongest_radio_null_holdout_rms_hz": strongest_radio_null,
        "holdout_advantage_over_strongest_radio_null_hz": strongest_radio_null - aggregate_orbit,
        "all_members_beat_best_polynomial": all(
            orbit < polynomial
            for orbit, polynomial in zip(member_orbit, member_polynomial, strict=True)
        ),
        "member_log_polynomial_mse_gains": member_gains,
        "named_association_statistic": statistic,
        "members": [
            {
                **fit,
                "path": member.path,
                "polynomial_nulls": polynomial,
                "orbit_beats_best_polynomial": float(fit["holdout_residual_rms_hz"])
                < float(polynomial["holdout_oracle_best_rms_hz"]),
            }
            for member, fit, polynomial in zip(
                members, best["member_fits"], polynomials, strict=True
            )
        ],
        "top_candidates": selected["top_candidates"],
    }


def empirical_p(true_value: float, control_values: list[float]) -> dict[str, Any]:
    if len(control_values) != 40:
        raise ValueError("the matched null requires exactly forty wrong-time values")
    exceedances = sum(value >= true_value for value in control_values)
    return {
        "true_value": float(true_value),
        "control_count": 40,
        "control_exceedance_count": int(exceedances),
        "empirical_p": float((1 + exceedances) / 41),
        "control_median": float(np.median(control_values)),
        "control_best": float(np.max(control_values)),
        "rule": "(1 + count(control >= true)) / 41",
    }


def _observer() -> ObserverSiteV1:
    return ObserverSiteV1(
        latitude_deg=cone.DEFAULT_LATITUDE_DEG,
        longitude_deg=cone.DEFAULT_LONGITUDE_DEG,
        altitude_m=cone.DEFAULT_ALTITUDE_M,
        label="reviewed-spinnaker-sausalito-not-capture-bound",
    )


def validate_tle(snapshot: FrozenFile) -> tuple[Any, dict[str, Any]]:
    if TLE_COLLECTED_UTC_NS >= CAPTURE_START_UTC_NS:
        raise ValueError("frozen TLE collection is not causal to the capture")
    expected_name = f"{TLE_COLLECTED_UTC_NS}-{TLE_DIGEST.removeprefix('sha256:')}.tle"
    if snapshot.path.name != expected_name:
        raise ValueError("TLE filename does not bind the frozen collection time and digest")
    catalogue = parse_element_sets(snapshot.payload.decode("ascii"))
    return catalogue, {
        "provider": "space-track",
        "digest": snapshot.digest,
        "collected_utc_ns": TLE_COLLECTED_UTC_NS,
        "capture_start_utc_ns": CAPTURE_START_UTC_NS,
        "collection_precedes_capture_s": (CAPTURE_START_UTC_NS - TLE_COLLECTED_UTC_NS)
        / 1_000_000_000,
        "catalogue_element_count": len(catalogue.names),
        "causal": True,
    }


def precalibration_checks(
    true_field: dict[str, Any],
    sensitivity: list[dict[str, Any]],
    alias_gates: dict[str, Any],
) -> dict[str, Any]:
    identities = {int(row["catalog_number"]) for row in sensitivity}
    epochs = {round(float(row["epoch_adjustment_s"]), 9) for row in sensitivity}
    true_epoch = round(float(true_field["epoch_adjustment_s"]), 9)
    return {
        "rx1_unique_strict_alias": bool(alias_gates["rx1_alias"]["unique_strict_replay_winner"]),
        "rx0_unique_strict_alias": bool(alias_gates["rx0_alias"]["unique_strict_replay_winner"]),
        "lossless_single_counter_segment": bool(alias_gates["rx1_counter_continuity"]["passed"]),
        "selected_candidate_train_visibility_eligible": bool(
            true_field["train_visibility_eligible"]
        ),
        "selected_candidate_holdout_visibility_eligible": bool(
            true_field["holdout_visibility_eligible"]
        ),
        "selected_candidate_full_visibility_eligible": bool(true_field["full_visibility_eligible"]),
        "epoch_interior": bool(true_field["epoch_interior"]),
        "every_member_orbit_beats_best_polynomial": bool(
            true_field["all_members_beat_best_polynomial"]
        ),
        "aggregate_orbit_holdout_rms_at_most_500_hz": bool(
            true_field["holdout_rms_hz"] <= MAXIMUM_HOLDOUT_RMS_HZ
        ),
        "aggregate_radio_null_advantage_at_least_100_hz": bool(
            true_field["holdout_advantage_over_strongest_radio_null_hz"]
            >= MINIMUM_POLYNOMIAL_ADVANTAGE_HZ
        ),
        "aggregate_orbit_beats_shared_curvature_null": bool(
            true_field["holdout_rms_hz"]
            < true_field["shared_curvature_null"]["holdout_oracle_best_rms_hz"]
        ),
        "training_runner_margin_at_least_100_hz": bool(
            true_field["runner_margin_hz"] >= MINIMUM_RUNNER_MARGIN_HZ
        ),
        "train_selected_identity_beats_every_alternative_on_holdout": bool(
            true_field["heldout_alternative_margin_hz"] > 0.0
        ),
        "heldout_alternative_margin_at_least_100_hz": bool(
            true_field["heldout_alternative_margin_hz"] >= MINIMUM_RUNNER_MARGIN_HZ
        ),
        "catalog_identity_stable_at_0_25_200_hz_s_drifts": bool(
            len(identities) == 1 and int(true_field["catalog_number"]) in identities
        ),
        "epoch_adjustment_stable_at_0_25_200_hz_s_drifts": bool(
            len(epochs) == 1 and true_epoch in epochs
        ),
    }


def calibrate_wrong_time_null(
    raw_diagnostic: dict[str, Any],
    true_field: dict[str, Any],
    sensitivity: list[dict[str, Any]],
    alias_gates: dict[str, Any],
) -> dict[str, Any]:
    checks = precalibration_checks(true_field, sensitivity, alias_gates)
    controls_complete = bool(raw_diagnostic["control_count"] == 40)
    eligible = bool(controls_complete and all(checks.values()))
    raw_p = float(raw_diagnostic["empirical_p"])
    rule = str(raw_diagnostic["rule"])
    return {
        **{
            key: value
            for key, value in raw_diagnostic.items()
            if key not in {"empirical_p", "rule"}
        },
        "raw_diagnostic_empirical_p": raw_p,
        "raw_diagnostic_rule": rule,
        "raw_diagnostic_interpretation": (
            "descriptive only; it cannot indicate identity specificity unless all hard "
            "pre-calibration gates pass"
        ),
        "precalibration_checks": checks,
        "identity_calibration_eligible": eligible,
        "identity_empirical_p": raw_p if eligible else None,
        "identity_empirical_p_status": "applicable" if eligible else "not_applicable",
        "identity_empirical_p_rule": rule if eligible else None,
        "identity_calibration_ineligibility_reasons": [
            name for name, passed in checks.items() if not passed
        ]
        + ([] if controls_complete else ["forty_matched_wrong_time_fields_complete"]),
    }


def numerical_gate(
    true_field: dict[str, Any],
    null: dict[str, Any],
    sensitivity: list[dict[str, Any]],
    alias_gates: dict[str, Any],
) -> dict[str, Any]:
    identity_p = null["identity_empirical_p"]
    checks = {
        **precalibration_checks(true_field, sensitivity, alias_gates),
        "forty_matched_wrong_time_fields_complete": bool(null["control_count"] == 40),
        "identity_calibration_eligible": bool(null["identity_calibration_eligible"]),
        "matched_wrong_time_identity_empirical_p_at_most_0p05": bool(
            identity_p is not None and identity_p <= MAXIMUM_WRONG_TIME_EMPIRICAL_P
        ),
    }
    return {"checks": checks, "passed": bool(all(checks.values()))}


def run_experiment(
    catalogue: Any,
    members: tuple[MemberSeries, MemberSeries],
    alias_gates: dict[str, Any],
    *,
    epoch_bound_s: float,
    horizon_deg: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    observer = _observer()
    polynomials = tuple(polynomial_null(member) for member in members)
    structural = shared_curvature_null(members)
    field_rows = []
    for field_index, shift_s in enumerate((0.0, *WRONG_TIME_SHIFTS_S)):
        field_started = time.perf_counter()
        field = prediction_field(
            catalogue,
            observer,
            field_shift_s=shift_s,
            epoch_bound_s=epoch_bound_s,
            horizon_deg=horizon_deg,
        )
        selected = select_common_candidate(
            members,
            field,
            epoch_bound_s=epoch_bound_s,
            drift_bound_hz_s=PRIMARY_DRIFT_BOUND_HZ_S,
        )
        finished = finish_field(selected, members, polynomials, structural, epoch_bound_s)
        field_rows.append(
            {
                "field_index": field_index,
                "time_shift_s": shift_s,
                "visible_catalogue_count": len(field.metadata),
                "runtime_s": time.perf_counter() - field_started,
                **finished,
            }
        )
    true_field = field_rows[0]
    controls = field_rows[1:]
    raw_diagnostic = empirical_p(
        float(true_field["named_association_statistic"]),
        [float(row["named_association_statistic"]) for row in controls],
    )

    true_prediction = prediction_field(
        catalogue,
        observer,
        field_shift_s=0.0,
        epoch_bound_s=epoch_bound_s,
        horizon_deg=horizon_deg,
    )
    sensitivity = []
    for bound in DRIFT_SENSITIVITY_BOUNDS_HZ_S:
        selected = select_common_candidate(
            members,
            true_prediction,
            epoch_bound_s=epoch_bound_s,
            drift_bound_hz_s=bound,
            retain_top=2,
        )
        sensitivity.append(
            {
                "drift_bound_hz_s": bound,
                "catalog_number": int(selected["best"]["catalog_number"]),
                "candidate_name": selected["best"]["object_name"],
                "epoch_adjustment_s": float(selected["best"]["epoch_adjustment_s"]),
                "train_rms_hz": float(selected["best"]["train_residual_rms_hz"]),
                "runner_margin_hz": float(
                    selected["runner"]["train_residual_rms_hz"]
                    - selected["best"]["train_residual_rms_hz"]
                ),
            }
        )
    null = calibrate_wrong_time_null(raw_diagnostic, true_field, sensitivity, alias_gates)
    gate = numerical_gate(true_field, null, sensitivity, alias_gates)
    return {
        "true_field": true_field,
        "wrong_time_null": null,
        "wrong_time_fields": controls,
        "drift_sensitivity": sensitivity,
        "numerical_identity_gate": gate,
        "runtime_s": time.perf_counter() - started,
    }


def _input_evidence(
    frozen_inputs: dict[str, FrozenFile], code: tuple[FrozenFile, ...]
) -> dict[str, Any]:
    return {
        "files": {
            label: {"path": str(snapshot.path), "sha256": snapshot.digest}
            for label, snapshot in frozen_inputs.items()
        },
        "code": {
            snapshot.label: {"path": str(snapshot.path), "sha256": snapshot.digest}
            for snapshot in code
        },
        "freeze_semantics": (
            "all input bytes and named executable sources were read and hashed at startup, "
            "all JSON was parsed from frozen bytes, and every path was rehashed before output"
        ),
    }


def _summary_markdown(evidence: dict[str, Any]) -> str:
    if evidence["status"] == "validated_inputs_only":
        return (
            "# 150802 alias-aware common-orbit input validation\n\n"
            "All exact radio, replay, continuity, code, and causal-TLE inputs passed validation. "
            "No orbit propagation or catalogue search was run.\n"
        )
    result = evidence["result"]
    true = result["true_field"]
    gate = result["numerical_identity_gate"]
    checks = "\n".join(
        f"- {'PASS' if passed else 'FAIL'} — `{name}`" for name, passed in gate["checks"].items()
    )
    null = result["wrong_time_null"]
    if null["identity_empirical_p_status"] == "applicable":
        calibration = (
            "The matched wrong-time identity empirical p-value was "
            f"{null['identity_empirical_p']:.5f} over forty complete controls."
        )
    else:
        calibration = (
            "The raw diagnostic matched wrong-time p-value was "
            f"{null['raw_diagnostic_empirical_p']:.5f}, but identity calibration was "
            "not applicable because hard pre-calibration gates failed. The raw diagnostic "
            "p-value cannot indicate identity specificity."
        )
    return f"""# 150802 alias-aware common-orbit audit

The training-only common winner was **{true["candidate_name"]} / {true["catalog_number"]}** at
{true["epoch_adjustment_s"]:+.2f} s. Aggregate train/holdout RMS was
{true["train_rms_hz"]:.2f}/{true["holdout_rms_hz"]:.2f} Hz; the training runner margin was
{true["runner_margin_hz"]:.2f} Hz. The numerical identity gate
**{"passed" if gate["passed"] else "failed"}**.

{checks}

{calibration}

## Interpretation limit

RX0 and RX1 are channels of the same Pluto and share a sample clock. This is channel
replication, not independent-instrument confirmation. Both trajectories and the RX1 direct
rows were selected using their full spans before this retrospective split. Even a numerical
pass would remain candidate-only and cannot promote a named physical transmitter identity.
"""


def write_evidence(output_root: Path, evidence: dict[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "alias-aware-common-orbit-evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_root / "alias-aware-common-orbit-summary.md").write_text(
        _summary_markdown(evidence), encoding="utf-8"
    )


def main() -> None:
    args = arguments()
    started = time.perf_counter()
    code = code_snapshots()
    frozen_inputs = freeze_inputs(args)
    catalogue, tle_evidence = validate_tle(frozen_inputs["tle_snapshot"])
    members, alias_gates = load_and_validate_members(frozen_inputs)
    if args.validate_inputs_only:
        result = None
        status = "validated_inputs_only"
    else:
        result = run_experiment(
            catalogue,
            members,
            alias_gates,
            epoch_bound_s=float(args.epoch_bound_s),
            horizon_deg=float(args.horizon_deg),
        )
        status = "complete"
    all_snapshots = (*code, *frozen_inputs.values())
    verify_frozen_files(all_snapshots)
    evidence = {
        "schema": "org.leo.research.alias-aware-common-orbit/v2",
        "status": status,
        "candidate_only": True,
        "session_id": SESSION_ID,
        "run_id": RUN_ID,
        "configuration": {
            "train_fraction": TRAIN_FRACTION,
            "shared_calendar_train_cutoff_s": alias_gates["train_cutoff_s"],
            "analysis_bin_width_s": BIN_WIDTH_S,
            "epoch_bound_s": float(args.epoch_bound_s),
            "epoch_step_s": EPOCH_STEP_S,
            "primary_per_receiver_drift_bound_hz_s": PRIMARY_DRIFT_BOUND_HZ_S,
            "drift_sensitivity_bounds_hz_s": list(DRIFT_SENSITIVITY_BOUNDS_HZ_S),
            "horizon_deg": float(args.horizon_deg),
            "minimum_visibility_fraction": MINIMUM_VISIBILITY_FRACTION,
            "visibility_roles": (
                "training rows alone determine candidate and epoch eligibility; "
                "holdout and full-span visibility are persisted prospective gates"
            ),
            "wrong_time_shifts_s": list(WRONG_TIME_SHIFTS_S),
            "receiver_aggregation": "equal member MSE; no raw-row-count weighting",
        },
        "tle_snapshot": tle_evidence,
        "input_validation": alias_gates,
        "frozen_provenance": _input_evidence(frozen_inputs, code),
        "result": result,
        "runtime_s": time.perf_counter() - started,
        "interpretation_limits": [
            (
                "RX0 and RX1 are channels of the same Pluto and share a sample clock; "
                "they are not independent instruments."
            ),
            (
                "Separate receiver offsets and bounded drifts do not remove shared-clock "
                "or common-front-end systematics."
            ),
            (
                "The fixed RX0 alias lift is a constant absorbed exactly by its separate "
                "intercept; it is an upstream replay prerequisite, not independent orbit "
                "information."
            ),
            (
                "Both replay-qualified trajectories were selected on their full spans "
                "before the retrospective 60/40 split."
            ),
            (
                "The RX1 direct CFO rows are trajectory-conditioned all-Qin GLRT "
                "selections, not iid frame observations."
            ),
            (
                "250 ms median bins limit cadence pseudoreplication but do not establish "
                "statistical independence."
            ),
            (
                "The degree-1/2/3 holdout oracle is a strong falsifier and never "
                "participates in TLE selection."
            ),
            (
                "The forty controls calibrate this focused post-hoc statistic only, "
                "not the family of prior identity searches."
            ),
            (
                "A numerical pass remains candidate-only and cannot promote a named "
                "physical transmitter identity."
            ),
        ],
    }
    write_evidence(args.output_root, evidence)


if __name__ == "__main__":
    main()
