#!/usr/bin/env python3
"""Audit post-refill edge pairs and replay conditional virtual switching.

The tool is intentionally product-only and read-only with respect to the radio
corpus.  It uses the frozen retrospective branch choices, then asks how much a
strict alternating lower/upper availability mask changes a joint rate fit.

Two persisted measurement layers are kept separate:

* dealiased GLRT observations consume complete 20 ms probes;
* receiver-local known-pilot CFO measurements use their exact pilot-symbol support.

The latter is an optimistic feasibility replay because its innovation gate was
computed by a full-track Kalman product.  Neither layer simulates Fast Lock
settling, phase return, or re-acquisition after a real retune.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S
from leo.storage import BulkUriResolver

DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
DEFAULT_RECORDINGS_ROOT = DEFAULT_BULK_ROOT / "recordings"
DEFAULT_RETROSPECTIVE = Path(
    "reports/2026_08_25_post_refill_24h_retrospective/retrospective-data.json"
)
DEFAULT_OUTPUT = Path(
    "reports/figures/2026_08_27_post_refill_edge_switching/edge-switching-results.json"
)
DEFAULT_REPORT = Path("reports/2026_08_27_post_refill_edge_switching.md")

# First authoritative post-refill same-channel opposite-edge capture, 193733.
POST_REFILL_OPPOSITE_EDGE_UTC_NS = 1_787_600_256_300_500_418
OPPOSITE_EDGE_POLICY_TAG = "tuning_policy:same_channel_opposite_edge"
SAME_FREQUENCY_POLICY_TAG = "tuning_policy:same"

EDGE_IF_HZ = {
    "ch1": {"lower": 959_687_500, "upper": 1_190_312_500},
    "ch2": {"lower": 1_209_687_500, "upper": 1_440_312_500},
    "ch3": {"lower": 1_459_687_500, "upper": 1_690_312_500},
    "ch4": {"lower": 1_709_687_500, "upper": 1_940_312_500},
}

PRIMARY_CAPTURE_IDS = (
    "cap-20260825T103607-9bd90a1a50e4",
    "cap-20260825T115401-774be9e8b225",
)

SCHEDULES = (
    ("2 guard + 7 valid frames", 9 / 750.0),
    ("2 guard + 15 valid frames", 17 / 750.0),
    ("2 guard + 30 valid frames", 32 / 750.0),
    ("100 ms dwell", 0.100),
    ("1 s dwell", 1.000),
)
GUARD_SECONDS = 2 / 750.0
FRAME_INNOVATION_GATE_HZ = 250.0


@dataclass(frozen=True, slots=True)
class CfoObservation:
    start_utc_ns: int
    duration_ns: int
    cfo_hz: float
    path_id: str
    stream_id: str
    edge: str
    estimate_utc_ns: int | None = None

    def __post_init__(self) -> None:
        if self.start_utc_ns < 0 or self.duration_ns <= 0:
            raise ValueError("CFO support interval is invalid")
        if self.edge not in {"lower", "upper"}:
            raise ValueError("CFO edge must be lower or upper")
        if self.estimate_utc_ns is not None and not (
            self.start_utc_ns <= self.estimate_utc_ns <= self.start_utc_ns + self.duration_ns
        ):
            raise ValueError("CFO estimate timestamp lies outside its support")

    @property
    def fit_utc_ns(self) -> int:
        if self.estimate_utc_ns is not None:
            return self.estimate_utc_ns
        return self.start_utc_ns + self.duration_ns // 2


@dataclass(frozen=True, slots=True)
class JointRateFit:
    observation_count: int
    path_count: int
    common_rate_hz_s: float
    differential_rate_hz_s: float
    lower_rate_hz_s: float
    upper_rate_hz_s: float
    residual_rms_hz: float
    residual_median_absolute_hz: float
    robust_scale_hz: float
    iteration_count: int
    converged: bool


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--recordings-root", type=Path, default=DEFAULT_RECORDINGS_ROOT)
    parser.add_argument("--retrospective", type=Path, default=DEFAULT_RETROSPECTIVE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--phase-count", type=int, default=256)
    parser.add_argument(
        "--skip-digest-verification",
        action="store_true",
        help="development-only escape hatch; published replay verifies every declared digest",
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _load(
    path: Path,
    *,
    expected_digest: str | None = None,
    verify_digest: bool = True,
) -> dict[str, Any]:
    if expected_digest is not None and verify_digest:
        actual = _sha256(path)
        if actual != expected_digest:
            raise ValueError(
                f"digest mismatch for {path}: expected {expected_digest}, got {actual}"
            )
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    payload = value.get("payload", value)
    if not isinstance(payload, dict):
        raise ValueError(f"expected object payload: {path}")
    return payload


def _product_document(
    product: dict[str, Any],
    *,
    resolver: BulkUriResolver,
    verify_digest: bool,
) -> dict[str, Any]:
    return _load(
        resolver.resolve(str(product["logical_uri"]), must_exist=True),
        expected_digest=str(product["digest"]),
        verify_digest=verify_digest,
    )


def _policy(tags: Sequence[str]) -> str | None:
    matches = [tag.split(":", 1)[1] for tag in tags if tag.startswith("tuning_policy:")]
    if len(matches) > 1:
        raise ValueError(f"manifest has multiple tuning policies: {matches}")
    return matches[0] if matches else None


def _tuning_by_stream(tags: Sequence[str]) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for tag in tags:
        if not tag.startswith("tuning:stream-"):
            continue
        fields = tag.split(":")
        if len(fields) != 4 or fields[2] not in EDGE_IF_HZ:
            raise ValueError(f"invalid tuning tag: {tag}")
        if fields[3] not in {"lower", "upper"}:
            raise ValueError(f"invalid Starlink edge tag: {tag}")
        result[fields[1]] = (fields[2], fields[3])
    return result


def _stream_observed_sample_count(stream: dict[str, Any]) -> int:
    """Read the observed count from either published stream schema generation."""

    if "observed_sample_count" in stream:
        return int(stream["observed_sample_count"])
    return int(stream["captured_sample_count"])


def _is_clean_continuity_capture(manifest: dict[str, Any]) -> bool:
    if manifest.get("state") != "committed":
        return False
    synchronization = manifest.get("synchronization", {})
    if int(synchronization.get("guaranteed_overlap_ns", 0)) <= 0:
        return False
    streams = manifest.get("streams", [])
    if len(streams) != 2:
        return False
    for stream in streams:
        continuity = stream.get("continuity", {})
        observed = int(continuity.get("observed_sample_count", -1))
        if (
            continuity.get("schema_version") != 2
            or continuity.get("sample_loss_observable") is not True
            or int(continuity.get("gap_count", -1)) != 0
            or int(continuity.get("missing_sample_count", -1)) != 0
            or int(continuity.get("overflow_count", -1)) != 0
            or int(continuity.get("segment_count", -1)) != 1
            or int(continuity.get("device_span_sample_count", -2)) != observed
            or _stream_observed_sample_count(stream) != observed
        ):
            return False
    return True


def discover_post_refill_inventory(recordings_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    paths = sorted(recordings_root.glob("2026/*/*/cap-*/manifest.json"))
    for path in paths:
        manifest = _load(path, verify_digest=False)
        tags = tuple(str(tag) for tag in manifest.get("tags", []))
        if OPPOSITE_EDGE_POLICY_TAG not in tags:
            continue
        streams = manifest.get("streams", [])
        if len(streams) != 2:
            continue
        first_utc_ns = min(
            int(stream["timing"]["first_sample"]["estimate_utc_ns"]) for stream in streams
        )
        if first_utc_ns < POST_REFILL_OPPOSITE_EDGE_UTC_NS:
            continue
        tuning = _tuning_by_stream(tags)
        if set(tuning) != {"stream-0", "stream-1"}:
            raise ValueError(f"missing opposite-edge tuning tags: {path}")
        channels = {value[0] for value in tuning.values()}
        edges = {value[1] for value in tuning.values()}
        if len(channels) != 1 or edges != {"lower", "upper"}:
            raise ValueError(f"policy/tag disagreement: {path}")
        channel = next(iter(channels))
        by_stream = {str(stream["stream_id"]): stream for stream in streams}
        for stream_id, (_, edge) in tuning.items():
            actual = int(by_stream[stream_id]["applied_settings"]["center_frequency_hz"])
            expected = EDGE_IF_HZ[channel][edge]
            if abs(actual - expected) > 5:
                raise ValueError(f"applied frequency disagrees with tuning tag: {path}")
        rates = {int(stream["applied_settings"]["sample_rate_hz"]) for stream in streams}
        if len(rates) != 1:
            raise ValueError(f"paired streams have different sample rates: {path}")
        synchronization = manifest["synchronization"]
        rows.append(
            {
                "session_id": path.parent.name,
                "manifest_path": str(path),
                "channel": channel,
                "stream_order": "/".join(tuning[f"stream-{i}"][1][0].upper() for i in range(2)),
                "sample_rate_hz": rates.pop(),
                "state": str(manifest["state"]),
                "clean": _is_clean_continuity_capture(manifest),
                "phase_coherent": bool(synchronization["phase_coherent"]),
                "synchronization_grade": str(synchronization["grade"]),
                "estimated_start_skew_ns": int(synchronization["estimated_start_skew_ns"]),
                "start_skew_uncertainty_ns": int(synchronization["start_skew_uncertainty_ns"]),
                "guaranteed_overlap_ns": int(synchronization["guaranteed_overlap_ns"]),
                "streams": [
                    {
                        "stream_id": str(stream["stream_id"]),
                        "radio_id": str(stream["radio"]["radio_id"]),
                        "edge": tuning[str(stream["stream_id"])][1],
                        "observed_sample_count": _stream_observed_sample_count(stream),
                        "first_device_sample_counter": int(
                            stream["continuity"]["first_device_sample_counter"]
                        ),
                        "last_device_sample_counter": int(
                            stream["continuity"]["last_device_sample_counter"]
                        ),
                        "gap_count": int(stream["continuity"]["gap_count"]),
                        "missing_sample_count": int(stream["continuity"]["missing_sample_count"]),
                        "segment_count": int(stream["continuity"]["segment_count"]),
                    }
                    for stream in streams
                ],
            }
        )
    return rows


def _products_by_scope(run_manifest: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for product in run_manifest.get("products", []):
        if not isinstance(product, dict) or product.get("status") not in {
            "complete",
            "partial_coverage",
        }:
            continue
        result.setdefault(str(product["scope_key"]), {})[str(product["kind"])] = product
    return result


def _kind(
    products: dict[str, dict[str, Any]], standard: str, research: str | None = None
) -> dict[str, Any] | None:
    return products.get(standard) or (products.get(research) if research else None)


def _path_products(
    run_manifest: dict[str, Any],
    *,
    resolver: BulkUriResolver,
    verify_digest: bool,
) -> dict[str, tuple[dict[str, dict[str, Any]], dict[str, Any]]]:
    result = {}
    for products in _products_by_scope(run_manifest).values():
        report_product = _kind(products, "standard.path-report", "research.path-report")
        if report_product is None:
            continue
        report = _product_document(report_product, resolver=resolver, verify_digest=verify_digest)
        raw = report.get("raw_report", {})
        if not isinstance(raw, dict):
            continue
        path_id = f"{raw['stream_id']}/{raw['radio_id']}/RX{raw['receiver_id']}"
        result[path_id] = (products, raw)
    return result


def _selected_path_summaries(
    retrospective_row: dict[str, Any],
    *,
    resolver: BulkUriResolver,
    verify_digest: bool,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    recording = _load(
        Path(str(retrospective_row["recording_manifest_path"])),
        expected_digest=str(retrospective_row["recording_manifest_digest"]),
        verify_digest=verify_digest,
    )
    run = _load(
        Path(str(retrospective_row["analysis_manifest_path"])),
        expected_digest=str(retrospective_row["analysis_manifest_digest"]),
        verify_digest=verify_digest,
    )
    path_products = _path_products(run, resolver=resolver, verify_digest=verify_digest)
    tuning = _tuning_by_stream(tuple(str(tag) for tag in recording.get("tags", [])))
    stream_map = {str(stream["stream_id"]): stream for stream in recording["streams"]}
    path_ids = str(retrospective_row["screen_path_ids"]).split(";")
    branch_ids = str(retrospective_row["screen_branch_ids"]).split(";")
    if len(path_ids) != len(branch_ids):
        raise ValueError("retrospective path and branch counts disagree")
    summaries = []
    for path_id, branch_id in zip(path_ids, branch_ids, strict=True):
        products, raw_report = path_products[path_id]
        bank_product = _kind(
            products,
            "standard.dealiased-trajectory-bank",
            "research.dealiased-trajectory-bank",
        )
        if bank_product is None:
            raise ValueError(f"selected path has no dealiased bank: {path_id}")
        bank = _product_document(bank_product, resolver=resolver, verify_digest=verify_digest)
        branches = [item for item in bank["branches"] if item["branch_id"] == branch_id]
        if len(branches) != 1:
            raise ValueError(f"selected branch is not unique: {branch_id}")
        branch = branches[0]
        stream_id = str(raw_report["stream_id"])
        stream = stream_map[stream_id]
        channel_edge = tuning.get(stream_id)
        edge = channel_edge[1] if channel_edge is not None else "same"
        lnb_hz = int(recording["capture_plan"]["profile_revision"]["profile"]["lnb_lo_hz"])
        summaries.append(
            {
                "path_id": path_id,
                "stream_id": stream_id,
                "radio_id": str(raw_report["radio_id"]),
                "receiver_id": int(raw_report["receiver_id"]),
                "edge": edge,
                "rf_hz": lnb_hz + int(stream["applied_settings"]["center_frequency_hz"]),
                "sample_rate_hz": int(raw_report["sample_rate_hz"]),
                "first_estimate_utc_ns": int(raw_report["timing"]["first_estimate_utc_ns"]),
                "branch_id": branch_id,
                "branch_start_s": float(branch["start_s"]),
                "branch_end_s": float(branch["end_s"]),
                "branch_slope_hz_s": float(branch["model"]["coefficients_hz"][0]),
                "branch_observation_count": len(branch["observation_ids"]),
                "branch": branch,
                "bank": bank,
                "products": products,
            }
        )
    return recording, run, summaries


def _weighted_mean(rows: Sequence[dict[str, Any]], field: str, weight: str) -> float:
    weights = np.asarray([float(row[weight]) for row in rows], dtype=np.float64)
    values = np.asarray([float(row[field]) for row in rows], dtype=np.float64)
    return float(np.average(values, weights=weights))


def summarize_selected_event(
    row: dict[str, Any],
    *,
    resolver: BulkUriResolver,
    verify_digest: bool,
) -> dict[str, Any]:
    recording, _run, paths = _selected_path_summaries(
        row, resolver=resolver, verify_digest=verify_digest
    )
    policy = _policy(tuple(str(tag) for tag in recording.get("tags", [])))
    result: dict[str, Any] = {
        "session_id": str(row["capture_session_id"]),
        "policy": policy,
        "path_count": len(paths),
        "common_overlap_s": float(row["screen_common_overlap_s"]),
        "normalized_slope_spread_hz_s": float(row["screen_normalized_slope_spread_hz_s"]),
        "qualified_pilot_segment_count": int(row["screen_qualified_pilot_segments"]),
        "analyzed_pilot_segment_count": int(row["screen_analyzed_pilot_segments"]),
        "paths": [
            {
                key: path[key]
                for key in (
                    "path_id",
                    "stream_id",
                    "radio_id",
                    "receiver_id",
                    "edge",
                    "rf_hz",
                    "branch_id",
                    "branch_slope_hz_s",
                    "branch_observation_count",
                )
            }
            for path in paths
        ],
    }
    if policy == "same_channel_opposite_edge":
        lower = [path for path in paths if path["edge"] == "lower"]
        upper = [path for path in paths if path["edge"] == "upper"]
        if not lower or not upper:
            raise ValueError("opposite-edge selection does not contain both edges")
        lower_rate = _weighted_mean(lower, "branch_slope_hz_s", "branch_observation_count")
        upper_rate = _weighted_mean(upper, "branch_slope_hz_s", "branch_observation_count")
        lower_rf = float(lower[0]["rf_hz"])
        upper_rf = float(upper[0]["rf_hz"])
        center_rf = (lower_rf + upper_rf) / 2.0
        separation = upper_rf - lower_rf
        common_rate = (lower_rate + upper_rate) / 2.0
        differential = upper_rate - lower_rate
        predicted = common_rate * separation / center_rf
        result.update(
            {
                "channel": next(
                    value[0] for value in _tuning_by_stream(recording["tags"]).values()
                ),
                "lower_rate_hz_s": lower_rate,
                "upper_rate_hz_s": upper_rate,
                "differential_rate_hz_s": differential,
                "pure_rf_scaling_prediction_hz_s": predicted,
                "pure_rf_scaling_residual_hz_s": differential - predicted,
                "closure_ratio": differential / predicted,
                "rf_center_hz": center_rf,
                "rf_separation_hz": separation,
                "stream0_edge": next(
                    path["edge"] for path in paths if path["stream_id"] == "stream-0"
                ),
            }
        )
    elif policy == "same":
        by_stream = {
            stream_id: [path for path in paths if path["stream_id"] == stream_id]
            for stream_id in {path["stream_id"] for path in paths}
        }
        if set(by_stream) == {"stream-0", "stream-1"}:
            rates = {
                stream_id: _weighted_mean(
                    stream_paths,
                    "branch_slope_hz_s",
                    "branch_observation_count",
                )
                for stream_id, stream_paths in by_stream.items()
            }
            result["stream_rates_hz_s"] = rates
            result["stream1_minus_stream0_rate_hz_s"] = rates["stream-1"] - rates["stream-0"]
    return result


def fit_joint_edge_rate(
    observations: Sequence[CfoObservation],
    *,
    scale_floor_hz: float,
    maximum_iterations: int = 40,
    prediction_tolerance_hz: float = 1e-6,
) -> JointRateFit:
    """Fit path intercepts, a common rate, and upper-minus-lower rate."""

    if not observations:
        raise ValueError("joint edge fit requires observations")
    edges = {item.edge for item in observations}
    if edges != {"lower", "upper"}:
        raise ValueError("joint edge fit requires lower and upper observations")
    paths = sorted({item.path_id for item in observations})
    counts = {path: sum(item.path_id == path for item in observations) for path in paths}
    if any(count < 3 for count in counts.values()):
        raise ValueError("joint edge fit requires at least three observations per path")
    path_index = {path: index for index, path in enumerate(paths)}
    reference_ns = int(np.median([item.fit_utc_ns for item in observations]))
    time_s = np.asarray(
        [(item.fit_utc_ns - reference_ns) / 1e9 for item in observations],
        dtype=np.float64,
    )
    values = np.asarray([item.cfo_hz for item in observations], dtype=np.float64)
    edge_sign = np.asarray(
        [1.0 if item.edge == "upper" else -1.0 for item in observations],
        dtype=np.float64,
    )
    design = np.zeros((len(observations), len(paths) + 2), dtype=np.float64)
    design[
        np.arange(len(observations)),
        [path_index[item.path_id] for item in observations],
    ] = 1.0
    design[:, -2] = time_s
    design[:, -1] = edge_sign * time_s / 2.0
    if np.linalg.matrix_rank(design) != design.shape[1]:
        raise ValueError("joint edge fit is rank deficient")

    coefficients = np.linalg.lstsq(design, values, rcond=None)[0]
    converged = False
    iteration_count = 0
    robust_scale = float(scale_floor_hz)
    for iteration_index in range(1, maximum_iterations + 1):
        iteration_count = iteration_index
        residual = values - design @ coefficients
        center = float(np.median(residual))
        mad = float(np.median(np.abs(residual - center)))
        robust_scale = max(float(scale_floor_hz), 1.4826 * mad)
        standardized = np.abs(residual) / robust_scale
        weights = np.ones_like(standardized)
        tail = standardized > 1.345
        weights[tail] = 1.345 / standardized[tail]
        root = np.sqrt(weights)
        updated = np.linalg.lstsq(design * root[:, None], values * root, rcond=None)[0]
        change = float(np.max(np.abs(design @ (updated - coefficients))))
        coefficients = updated
        if change <= prediction_tolerance_hz:
            converged = True
            break
    residual = values - design @ coefficients
    common_rate = float(coefficients[-2])
    differential = float(coefficients[-1])
    return JointRateFit(
        observation_count=len(observations),
        path_count=len(paths),
        common_rate_hz_s=common_rate,
        differential_rate_hz_s=differential,
        lower_rate_hz_s=common_rate - differential / 2.0,
        upper_rate_hz_s=common_rate + differential / 2.0,
        residual_rms_hz=float(np.sqrt(np.mean(residual**2))),
        residual_median_absolute_hz=float(np.median(np.abs(residual))),
        robust_scale_hz=robust_scale,
        iteration_count=iteration_count,
        converged=converged,
    )


def _coarse_observations(
    paths: Sequence[dict[str, Any]],
    *,
    resolver: BulkUriResolver,
    verify_digest: bool,
) -> tuple[list[CfoObservation], int, int]:
    observations: list[CfoObservation] = []
    intervals = []
    for path in paths:
        schedule_product = _kind(
            path["products"], "standard.probe-schedule", "research.probe-schedule"
        )
        if schedule_product is None:
            raise ValueError(f"path has no probe schedule: {path['path_id']}")
        schedule = _product_document(
            schedule_product, resolver=resolver, verify_digest=verify_digest
        )
        sample_rate_hz = int(schedule["sample_rate_hz"])
        duration_by_start = {
            int(probe["sample_start"]): math.ceil(int(probe["sample_count"]) * 1e9 / sample_rate_hz)
            for probe in schedule["probes"]
        }
        first_ns = int(path["first_estimate_utc_ns"])
        intervals.append(
            (
                first_ns + round(float(path["branch_start_s"]) * 1e9),
                first_ns + round(float(path["branch_end_s"]) * 1e9),
            )
        )
        ids = set(path["branch"]["observation_ids"])
        for item in path["bank"]["observations"]:
            if item["observation_id"] not in ids:
                continue
            sample_start = int(item["sample_start"])
            observations.append(
                CfoObservation(
                    start_utc_ns=first_ns + round(float(item["time_s"]) * 1e9),
                    duration_ns=duration_by_start[sample_start],
                    cfo_hz=float(item["component_cfo_hz"]),
                    path_id=str(path["path_id"]),
                    stream_id=str(path["stream_id"]),
                    edge=str(path["edge"]),
                )
            )
    common_start = max(item[0] for item in intervals)
    common_end = min(item[1] for item in intervals)
    retained = [
        item
        for item in observations
        if item.start_utc_ns >= common_start and item.start_utc_ns + item.duration_ns <= common_end
    ]
    return retained, common_start, common_end


def _pilot_support_sample_offsets(
    sample_rate_hz: int,
    pilot_symbol_count: int,
) -> tuple[int, int]:
    if sample_rate_hz <= 0 or not 8 <= pilot_symbol_count <= 300:
        raise ValueError("invalid known-pilot support geometry")
    return (
        round(2 * sample_rate_hz * OFDM_SYMBOL_DURATION_S),
        round((2 + pilot_symbol_count) * sample_rate_hz * OFDM_SYMBOL_DURATION_S),
    )


def _fine_observations(
    paths: Sequence[dict[str, Any]],
    *,
    resolver: BulkUriResolver,
    verify_digest: bool,
) -> tuple[list[CfoObservation], int, int, list[dict[str, Any]]]:
    observations: list[CfoObservation] = []
    intervals = []
    track_inventory = []
    for path in paths:
        kalman_product = _kind(path["products"], "standard.kalman-tracking")
        pilot_product = _kind(path["products"], "standard.pilot-doppler-segments")
        if kalman_product is None or pilot_product is None:
            raise ValueError(f"path lacks fine pilot products: {path['path_id']}")
        kalman = _product_document(kalman_product, resolver=resolver, verify_digest=verify_digest)
        pilot = _product_document(pilot_product, resolver=resolver, verify_digest=verify_digest)
        qualified = {
            str(item["source_trajectory_id"]): int(item["qualified_segment_count"])
            for item in pilot["trajectory_summaries"]
            if item["source_branch_id"] == path["branch_id"]
        }
        tracks = [
            item for item in kalman["tracks"] if item["source_branch_id"] == path["branch_id"]
        ]
        if not tracks:
            raise ValueError(f"selected branch has no Kalman track: {path['branch_id']}")
        track = max(
            tracks,
            key=lambda item: (
                qualified.get(str(item["source_trajectory_id"]), 0),
                int(item["measurement_update_count"]),
                int(item["returned_frame_count"]),
            ),
        )
        frames = [
            frame
            for frame in track["frames"]
            if frame.get("measurement_doppler_hz") is not None
            and frame.get("update_applied") is True
            and abs(float(frame["doppler_innovation_hz"])) <= FRAME_INNOVATION_GATE_HZ
        ]
        if not frames:
            raise ValueError(f"selected track has no gated frame measurements: {path['path_id']}")
        first_ns = int(path["first_estimate_utc_ns"])
        sample_rate_hz = int(path["sample_rate_hz"])
        pilot_symbol_count = int(kalman["config"]["pilot_symbol_count"])
        first_pilot_sample, final_pilot_sample = _pilot_support_sample_offsets(
            sample_rate_hz,
            pilot_symbol_count,
        )
        path_observations = []
        for frame in frames:
            frame_sample = int(frame["sample_start"])
            support_start_ns = first_ns + (
                (frame_sample + first_pilot_sample) * 1_000_000_000 // sample_rate_hz
            )
            support_end_numerator = (frame_sample + final_pilot_sample) * 1_000_000_000
            support_end_ns = (
                first_ns + (support_end_numerator + sample_rate_hz - 1) // sample_rate_hz
            )
            path_observations.append(
                CfoObservation(
                    start_utc_ns=support_start_ns,
                    duration_ns=support_end_ns - support_start_ns,
                    estimate_utc_ns=first_ns + round(float(frame["time_s"]) * 1e9),
                    cfo_hz=float(frame["measurement_doppler_hz"]),
                    path_id=str(path["path_id"]),
                    stream_id=str(path["stream_id"]),
                    edge=str(path["edge"]),
                )
            )
        observations.extend(path_observations)
        intervals.append(
            (
                min(item.start_utc_ns for item in path_observations),
                max(item.start_utc_ns + item.duration_ns for item in path_observations),
            )
        )
        track_inventory.append(
            {
                "path_id": path["path_id"],
                "source_trajectory_id": track["source_trajectory_id"],
                "qualified_pilot_segment_count": qualified.get(
                    str(track["source_trajectory_id"]), 0
                ),
                "returned_frame_count": int(track["returned_frame_count"]),
                "gated_measurement_count": len(frames),
                "pilot_support_duration_us": (final_pilot_sample - first_pilot_sample)
                * 1e6
                / sample_rate_hz,
            }
        )
    common_start = max(item[0] for item in intervals)
    common_end = min(item[1] for item in intervals)
    retained = [
        item
        for item in observations
        if item.start_utc_ns >= common_start and item.start_utc_ns + item.duration_ns <= common_end
    ]
    return retained, common_start, common_end, track_inventory


def strict_schedule_mask(
    observations: Sequence[CfoObservation],
    *,
    dwell_ns: int,
    guard_ns: int,
    phase_ns: int,
) -> list[CfoObservation]:
    """Keep measurements wholly contained in the scheduled valid edge interval."""

    if dwell_ns <= 0 or guard_ns < 0 or guard_ns >= dwell_ns:
        raise ValueError("invalid switching schedule")
    cycle_ns = 2 * dwell_ns
    retained = []
    for item in observations:
        position = (item.start_utc_ns - phase_ns) % cycle_ns
        if position < dwell_ns:
            active_edge = "lower"
            within_dwell = position
        else:
            active_edge = "upper"
            within_dwell = position - dwell_ns
        if (
            item.edge == active_edge
            and within_dwell >= guard_ns
            and within_dwell + item.duration_ns <= dwell_ns
        ):
            retained.append(item)
    return retained


def evaluate_virtual_schedules(
    observations: Sequence[CfoObservation],
    *,
    scale_floor_hz: float,
    phase_count: int,
) -> dict[str, Any]:
    if phase_count < 8:
        raise ValueError("phase sweep requires at least eight phases")
    baseline = fit_joint_edge_rate(observations, scale_floor_hz=scale_floor_hz)
    baseline_edge_counts = {
        edge: sum(item.edge == edge for item in observations) for edge in ("lower", "upper")
    }
    baseline_path_counts = {
        path_id: sum(item.path_id == path_id for item in observations)
        for path_id in sorted({item.path_id for item in observations})
    }
    guard_ns = round(GUARD_SECONDS * 1e9)
    maximum_duration_ns = max(item.duration_ns for item in observations)
    rows = []
    for label, dwell_s in SCHEDULES:
        dwell_ns = round(dwell_s * 1e9)
        start_slack_ns = dwell_ns - guard_ns - maximum_duration_ns
        if start_slack_ns <= 0:
            rows.append(
                {
                    "label": label,
                    "dwell_s": dwell_s,
                    "guard_s": GUARD_SECONDS,
                    "measurement_duration_s": maximum_duration_ns / 1e9,
                    "valid_start_slack_s": start_slack_ns / 1e9,
                    "status": "not_resolvable_from_measurement_duration",
                    "feasible_phase_count": 0,
                    "requested_phase_count": phase_count,
                }
            )
            continue
        deviations = []
        retained_counts = []
        retained_edge_counts = {"lower": [], "upper": []}
        minimum_path_counts = []
        minimum_path_spans_s = []
        phases = sorted({round(index * 2 * dwell_ns / phase_count) for index in range(phase_count)})
        for phase_ns in phases:
            masked = strict_schedule_mask(
                observations,
                dwell_ns=dwell_ns,
                guard_ns=guard_ns,
                phase_ns=phase_ns,
            )
            try:
                fitted = fit_joint_edge_rate(masked, scale_floor_hz=scale_floor_hz)
            except (ValueError, np.linalg.LinAlgError):
                continue
            deviations.append(fitted.differential_rate_hz_s - baseline.differential_rate_hz_s)
            retained_counts.append(len(masked))
            for edge in ("lower", "upper"):
                retained_edge_counts[edge].append(sum(item.edge == edge for item in masked))
            path_groups = {
                path_id: [item for item in masked if item.path_id == path_id]
                for path_id in baseline_path_counts
            }
            minimum_path_counts.append(
                min(len(path_observations) for path_observations in path_groups.values())
            )
            minimum_path_spans_s.append(
                min(
                    (
                        (
                            max(item.fit_utc_ns for item in path_observations)
                            - min(item.fit_utc_ns for item in path_observations)
                        )
                        / 1e9
                        if len(path_observations) >= 2
                        else 0.0
                    )
                    for path_observations in path_groups.values()
                )
            )
        if not deviations:
            rows.append(
                {
                    "label": label,
                    "dwell_s": dwell_s,
                    "guard_s": GUARD_SECONDS,
                    "measurement_duration_s": maximum_duration_ns / 1e9,
                    "valid_start_slack_s": start_slack_ns / 1e9,
                    "status": "no_estimable_schedule_phase",
                    "feasible_phase_count": 0,
                    "requested_phase_count": phase_count,
                }
            )
            continue
        absolute = np.abs(np.asarray(deviations, dtype=np.float64))
        counts = np.asarray(retained_counts, dtype=np.float64)
        lower_counts = np.asarray(retained_edge_counts["lower"], dtype=np.float64)
        upper_counts = np.asarray(retained_edge_counts["upper"], dtype=np.float64)
        path_counts = np.asarray(minimum_path_counts, dtype=np.float64)
        path_spans = np.asarray(minimum_path_spans_s, dtype=np.float64)
        rows.append(
            {
                "label": label,
                "dwell_s": dwell_s,
                "guard_s": GUARD_SECONDS,
                "measurement_duration_s": maximum_duration_ns / 1e9,
                "valid_start_slack_s": start_slack_ns / 1e9,
                "status": "complete",
                "feasible_phase_count": len(deviations),
                "requested_phase_count": phase_count,
                "feasible_phase_fraction": len(deviations) / len(phases),
                "retained_observation_count_median": float(np.median(counts)),
                "retained_fraction_median": float(np.median(counts) / len(observations)),
                "retained_lower_observation_count_median": float(np.median(lower_counts)),
                "retained_lower_observation_count_minimum": int(np.min(lower_counts)),
                "retained_upper_observation_count_median": float(np.median(upper_counts)),
                "retained_upper_observation_count_minimum": int(np.min(upper_counts)),
                "retained_lower_fraction_of_baseline_median": float(
                    np.median(lower_counts) / baseline_edge_counts["lower"]
                ),
                "retained_upper_fraction_of_baseline_median": float(
                    np.median(upper_counts) / baseline_edge_counts["upper"]
                ),
                "minimum_path_observation_count_median": float(np.median(path_counts)),
                "minimum_path_observation_count_minimum": int(np.min(path_counts)),
                "minimum_path_time_span_s_median": float(np.median(path_spans)),
                "minimum_path_time_span_s_minimum": float(np.min(path_spans)),
                "signed_masked_minus_unmasked_rate_deviation_median_hz_s": float(
                    np.median(deviations)
                ),
                "absolute_masked_minus_unmasked_rate_deviation_median_hz_s": float(
                    np.median(absolute)
                ),
                "absolute_masked_minus_unmasked_rate_deviation_p90_hz_s": float(
                    np.percentile(absolute, 90)
                ),
                "absolute_masked_minus_unmasked_rate_deviation_max_hz_s": float(np.max(absolute)),
            }
        )
    baseline_document = asdict(baseline)
    baseline_document["observation_count_by_edge"] = baseline_edge_counts
    baseline_document["observation_count_by_path"] = baseline_path_counts
    return {"baseline": baseline_document, "schedules": rows}


def evaluate_relative_timing_sensitivity(
    observations: Sequence[CfoObservation],
    *,
    upper_timing_uncertainty_ns: int,
    scale_floor_hz: float,
    phase_count: int,
) -> dict[str, Any]:
    """Replay a bounded relative UTC-anchor shift between the two radios."""

    offsets_ns = sorted(
        {round(fraction * upper_timing_uncertainty_ns) for fraction in (-1.0, -0.5, 0.0, 0.5, 1.0)}
    )
    replays = []
    for offset_ns in offsets_ns:
        shifted = [
            replace(
                item,
                start_utc_ns=item.start_utc_ns + offset_ns,
                estimate_utc_ns=(
                    item.estimate_utc_ns + offset_ns if item.estimate_utc_ns is not None else None
                ),
            )
            if item.edge == "upper"
            else item
            for item in observations
        ]
        replay = evaluate_virtual_schedules(
            shifted,
            scale_floor_hz=scale_floor_hz,
            phase_count=phase_count,
        )
        replays.append({"upper_offset_ns": offset_ns, **replay})

    uncertainty_envelope = [
        replace(
            item,
            start_utc_ns=item.start_utc_ns - upper_timing_uncertainty_ns,
            duration_ns=item.duration_ns + 2 * upper_timing_uncertainty_ns,
        )
        if item.edge == "upper"
        else item
        for item in observations
    ]
    envelope_replay = evaluate_virtual_schedules(
        uncertainty_envelope,
        scale_floor_hz=scale_floor_hz,
        phase_count=phase_count,
    )

    schedule_rows = []
    for index, (label, dwell_s) in enumerate(SCHEDULES):
        eligible = [
            replay["schedules"][index]
            for replay in replays
            if replay["schedules"][index]["status"] == "complete"
        ]
        envelope = envelope_replay["schedules"][index]
        schedule_rows.append(
            {
                "label": label,
                "dwell_s": dwell_s,
                "status": "complete" if eligible else "not_resolvable",
                "worst_p90_masked_minus_unmasked_rate_deviation_hz_s": (
                    max(
                        float(row["absolute_masked_minus_unmasked_rate_deviation_p90_hz_s"])
                        for row in eligible
                    )
                    if eligible
                    else None
                ),
                "uncertainty_envelope_status": envelope["status"],
                "uncertainty_envelope_retained_fraction_median": envelope.get(
                    "retained_fraction_median"
                ),
                "uncertainty_envelope_retained_lower_fraction_of_baseline_median": (
                    envelope.get("retained_lower_fraction_of_baseline_median")
                ),
                "uncertainty_envelope_retained_upper_fraction_of_baseline_median": (
                    envelope.get("retained_upper_fraction_of_baseline_median")
                ),
                "uncertainty_envelope_p90_masked_minus_unmasked_rate_deviation_hz_s": (
                    envelope.get("absolute_masked_minus_unmasked_rate_deviation_p90_hz_s")
                ),
            }
        )
    return {
        "upper_timing_uncertainty_ns": upper_timing_uncertainty_ns,
        "tested_upper_offsets_ns": offsets_ns,
        "baseline_differential_rates_hz_s": [
            float(replay["baseline"]["differential_rate_hz_s"]) for replay in replays
        ],
        "schedules": schedule_rows,
    }


def _percentiles(values: Iterable[float]) -> dict[str, float]:
    array = np.asarray(tuple(values), dtype=np.float64)
    if not array.size:
        return {}
    return {
        "minimum": float(np.min(array)),
        "p10": float(np.percentile(array, 10)),
        "median": float(np.median(array)),
        "p90": float(np.percentile(array, 90)),
        "maximum": float(np.max(array)),
    }


def build_results(
    *,
    bulk_root: Path,
    recordings_root: Path,
    retrospective_path: Path,
    verify_digest: bool,
    phase_count: int,
) -> dict[str, Any]:
    resolver = BulkUriResolver(
        bulk_root,
        allowed_namespaces=("analysis",),
        create=False,
    )
    inventory = discover_post_refill_inventory(recordings_root)
    clean = [row for row in inventory if row["clean"]]
    degraded = [row for row in inventory if not row["clean"]]
    clean_rates: dict[str, int] = {}
    for row in clean:
        key = str(row["sample_rate_hz"])
        clean_rates[key] = clean_rates.get(key, 0) + 1

    retrospective = _load(retrospective_path, verify_digest=False)
    rows = list(retrospective["captures"])
    edge_rows = []
    same_rows = []
    for row in rows:
        if not row.get("screen_branch_ids") or not row.get("screen_path_ids"):
            continue
        recording = _load(Path(str(row["recording_manifest_path"])), verify_digest=False)
        policy = _policy(tuple(str(tag) for tag in recording.get("tags", [])))
        if (
            policy == "same_channel_opposite_edge"
            and row.get("screen_band_relationship") == "cross-band"
        ):
            edge_rows.append(
                summarize_selected_event(row, resolver=resolver, verify_digest=verify_digest)
            )
        elif policy == "same" and row.get("screen_band_relationship") == "same-band":
            same_rows.append(
                summarize_selected_event(row, resolver=resolver, verify_digest=verify_digest)
            )

    same_differences = [
        float(row["stream1_minus_stream0_rate_hz_s"])
        for row in same_rows
        if "stream1_minus_stream0_rate_hz_s" in row
    ]
    closure = [float(row["closure_ratio"]) for row in edge_rows]
    scaling_residual = [float(row["pure_rf_scaling_residual_hz_s"]) for row in edge_rows]

    prototype_cases = {}
    retrospective_by_id = {str(row["capture_session_id"]): row for row in rows}
    for session_id in PRIMARY_CAPTURE_IDS:
        row = retrospective_by_id[session_id]
        recording, _run, paths = _selected_path_summaries(
            row, resolver=resolver, verify_digest=verify_digest
        )
        coarse, coarse_start, coarse_end = _coarse_observations(
            paths, resolver=resolver, verify_digest=verify_digest
        )
        case: dict[str, Any] = {
            "session_id": session_id,
            "recording_manifest_path": str(row["recording_manifest_path"]),
            "phase_coherent": bool(recording["synchronization"]["phase_coherent"]),
            "estimated_start_skew_ns": int(recording["synchronization"]["estimated_start_skew_ns"]),
            "start_skew_uncertainty_ns": int(
                recording["synchronization"]["start_skew_uncertainty_ns"]
            ),
            "selected_common_overlap_s": float(row["screen_common_overlap_s"]),
            "coarse_joint_overlap_s": (coarse_end - coarse_start) / 1e9,
            "coarse": evaluate_virtual_schedules(
                coarse, scale_floor_hz=100.0, phase_count=phase_count
            ),
        }
        if session_id.endswith("774be9e8b225"):
            fine, fine_start, fine_end, tracks = _fine_observations(
                paths, resolver=resolver, verify_digest=verify_digest
            )
            fine_replay = evaluate_virtual_schedules(
                fine, scale_floor_hz=25.0, phase_count=phase_count
            )
            case["fine"] = {
                "measurement_semantics": (
                    "receiver-local known-pilot measurement_doppler_hz; update_applied; "
                    f"absolute innovation <= {FRAME_INNOVATION_GATE_HZ:.0f} Hz"
                ),
                "selection_warning": (
                    "the innovation gate and trajectory identity were computed from the "
                    "full recording, so this is an optimistic availability replay"
                ),
                "joint_overlap_s": (fine_end - fine_start) / 1e9,
                "track_inventory": tracks,
                **fine_replay,
                "relative_timing_sensitivity": evaluate_relative_timing_sensitivity(
                    fine,
                    upper_timing_uncertainty_ns=int(
                        recording["synchronization"]["start_skew_uncertainty_ns"]
                    ),
                    scale_floor_hz=25.0,
                    phase_count=phase_count,
                ),
            }
        prototype_cases[session_id] = case

    return {
        "schema": "org.leo.research.post-refill-edge-switching/v1",
        "method": {
            "joint_model": (
                "z_i = path_intercept + common_rate*t + edge_sign*differential_rate*t/2 + residual"
            ),
            "edge_sign": {"lower": -1, "upper": 1},
            "observable_name": "receiver/path-conditional edge-group slope contrast",
            "guard_s": GUARD_SECONDS,
            "phase_count": phase_count,
            "mask_rule": "measurement interval must be wholly inside the valid dwell",
            "schedule_statistic": (
                f"quantiles across {phase_count} prespecified uniformly spaced phase "
                "offsets of the absolute masked-minus-unmasked edge-group slope contrast; "
                "not estimator accuracy or uncertainty"
            ),
            "retrospective_selection_warning": (
                "branches were frozen after an RF-normalized slope-agreement screen; "
                "closure is descriptive and post-selection"
            ),
        },
        "inventory": {
            "technical_cutoff_utc_ns": POST_REFILL_OPPOSITE_EDGE_UTC_NS,
            "capture_count": len(inventory),
            "clean_capture_count": len(clean),
            "degraded_capture_count": len(degraded),
            "clean_counts_by_sample_rate_hz": clean_rates,
            "phase_coherent_capture_count": sum(bool(row["phase_coherent"]) for row in inventory),
            "clean_start_skew_ms": _percentiles(
                row["estimated_start_skew_ns"] / 1e6 for row in clean
            ),
            "clean_start_skew_uncertainty_ms": _percentiles(
                row["start_skew_uncertainty_ns"] / 1e6 for row in clean
            ),
            "clean_guaranteed_overlap_s": _percentiles(
                row["guaranteed_overlap_ns"] / 1e9 for row in clean
            ),
            "captures": inventory,
        },
        "retrospective": {
            "source": str(retrospective_path),
            "source_digest": _sha256(retrospective_path),
            "selected_opposite_edge_event_count": len(edge_rows),
            "selected_same_frequency_control_count": len(same_differences),
            "opposite_edge_closure_ratio": _percentiles(closure),
            "opposite_edge_scaling_residual_hz_s": {
                **_percentiles(scaling_residual),
                "rms": float(np.sqrt(np.mean(np.asarray(scaling_residual) ** 2))),
            },
            "same_frequency_stream_difference_hz_s": {
                **_percentiles(same_differences),
                "median_absolute": float(np.median(np.abs(same_differences))),
                "p90_absolute": float(np.percentile(np.abs(same_differences), 90)),
                "rms": float(np.sqrt(np.mean(np.asarray(same_differences) ** 2))),
            },
            "opposite_edge_events": edge_rows,
        },
        "prototype_cases": prototype_cases,
        "interpretation_limits": [
            "cross-radio counters have independent epochs and cannot be subtracted",
            "the manifests explicitly declare phase_coherent=false",
            "no decoded payload or absolute Starlink frame counter proves satellite identity",
            "two-radio differential rate includes differential LNB/radio reference drift",
            "virtual masks do not simulate Fast Lock settling, phase return, or re-acquisition",
            "masked-minus-unmasked phase quantiles are conditional deviations, not accuracy",
            "full-data branch, alias, and Kalman decisions oracle-condition the replay",
            "linear-fit deviations can include curvature-induced temporal reweighting",
            "coherent 230.625 MHz synthetic-bandwidth TOA is not evaluated",
        ],
    }


def _schedule_lookup(case: dict[str, Any], layer: str) -> list[dict[str, Any]]:
    return list(case[layer]["schedules"])


def write_report(path: Path, results: dict[str, Any], output_path: Path) -> None:
    inventory = results["inventory"]
    retrospective = results["retrospective"]
    phase_count = int(results["method"]["phase_count"])
    cases = results["prototype_cases"]
    primary = cases["cap-20260825T115401-774be9e8b225"]
    replication = cases["cap-20260825T103607-9bd90a1a50e4"]
    event_by_id = {row["session_id"]: row for row in retrospective["opposite_edge_events"]}
    candidate_ids = (
        "cap-20260825T085623-c725d27cbf0f",
        "cap-20260825T103607-9bd90a1a50e4",
        "cap-20260825T115401-774be9e8b225",
        "cap-20260825T130425-1678069fefd1",
        "cap-20260825T101702-f60463e1402e",
    )
    fine_12_ms = next(
        row for row in primary["fine"]["schedules"] if abs(row["dwell_s"] - 0.012) < 1e-6
    )
    timing_sensitivity = primary["fine"]["relative_timing_sensitivity"]
    fine_timing_by_label = {row["label"]: row for row in timing_sensitivity["schedules"]}
    fine_12_ms_timing = fine_timing_by_label[fine_12_ms["label"]]
    fine_baseline_edge_counts = primary["fine"]["baseline"]["observation_count_by_edge"]
    fine_12_envelope_p90 = fine_12_ms_timing[
        "uncertainty_envelope_p90_masked_minus_unmasked_rate_deviation_hz_s"
    ]
    output_link = os.path.relpath(output_path.resolve(), path.parent.resolve())
    lines = [
        "# Post-refill upper/lower synchronization and switching replay",
        "",
        "## Outcome",
        "",
        f"The corpus contains **{inventory['capture_count']}** authoritative same-channel "
        "opposite-edge captures after the refill correction. "
        f"**{inventory['clean_capture_count']}** "
        "are gap-free and counter-complete; the three 5 MS/s attempts are degraded and are "
        "excluded from the replay. None is phase coherent.",
        "",
        "The clean captures provide continuous per-radio counters and enough overlapping "
        "duration for receiver-local multi-second slope comparisons: their median guaranteed "
        "overlap is "
        f"{inventory['clean_guaranteed_overlap_s']['median']:.6f} s. "
        "They are not sample-aligned across radios. Each FPGA counter is authoritative only "
        "inside its own radio, and the manifest UTC anchors carry millisecond uncertainty.",
        "",
        "A conditional product-availability replay is encouraging. On `115401`, a 12 ms "
        "virtual dwell applied to receiver-local frame CFO measurements has a "
        "90th-percentile masked-minus-unmasked edge-group slope deviation of "
        f"{fine_12_ms['absolute_masked_minus_unmasked_rate_deviation_p90_hz_s']:.2f} Hz/s "
        f"across the {phase_count} prespecified uniformly spaced phase offsets. Retaining "
        "only upper-edge measurements whose support remains valid throughout the declared "
        "relative-UTC interval raises it to "
        f"{fine_12_envelope_p90:.2f} Hz/s. "
        "This is not estimator accuracy, uncertainty, or a Fast Lock hardware result.",
        "",
        "## Capture inventory",
        "",
        "| Rate | Clean | Degraded | Use |",
        "|---:|---:|---:|---|",
    ]
    for rate in (2_500_000, 3_000_000, 5_000_000):
        clean_count = sum(
            row["clean"] and row["sample_rate_hz"] == rate for row in inventory["captures"]
        )
        degraded_count = sum(
            not row["clean"] and row["sample_rate_hz"] == rate for row in inventory["captures"]
        )
        use = (
            "primary analyzed corpus"
            if rate == 2_500_000
            else "clean follow-up; one native analyzed capture"
            if rate == 3_000_000
            else "exclude: large missing-sample gaps"
        )
        lines.append(f"| {rate / 1e6:g} MS/s | {clean_count} | {degraded_count} | {use} |")
    lines.extend(
        [
            "",
            "All clean streams have continuity schema v2, observable loss, one segment, "
            "zero reported gaps/overflows, and a device-counter span exactly equal to the "
            "captured sample count. `phase_coherent=false` for all 34 pairs.",
            "",
            "## Existing same-event candidates",
            "",
            "The frozen retrospective contains 22 deliberate opposite-edge captures with a "
            "selected cross-edge branch set. These are post-selected concurrent candidate "
            "tracks consistent with RF scaling under the same-satellite working assumption; "
            "they do not prove spacecraft identity.",
            "",
            "| Capture | CH | Paths / overlap | Lower rate | Upper rate | U−L | "
            "Pure RF scaling | Closure |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for session_id in candidate_ids:
        row = event_by_id[session_id]
        short = session_id.split("T", 1)[1][:6]
        lines.append(
            f"| `{short}` | {row['channel'].upper()} | {row['path_count']} / "
            f"{row['common_overlap_s']:.3f} s | {row['lower_rate_hz_s']:.2f} | "
            f"{row['upper_rate_hz_s']:.2f} | {row['differential_rate_hz_s']:.2f} | "
            f"{row['pure_rf_scaling_prediction_hz_s']:.2f} | {row['closure_ratio']:.3f} |"
        )
    lines.extend(
        [
            "",
            "The closure calculation is descriptive: the retrospective chose branch sets "
            "partly by RF-normalized slope agreement. A confirmatory result must freeze "
            "identity on a training interval and score upper/lower scaling on held-out time.",
            "",
            "![Observed versus RF-scaled edge-group slope contrast]"
            "(figures/2026_08_27_post_refill_edge_switching/opposite-edge-closure.png)",
            "",
            "*The 22 points are post-selected by an RF-normalized slope-agreement screen; "
            "the identity line is a descriptive reference, not independent validation.*",
            "",
            "The 28 post-selected same-frequency controls show the scale of the two-radio "
            "nuisance distribution. Their "
            f"stream-1-minus-stream-0 rate difference has "
            f"{retrospective['same_frequency_stream_difference_hz_s']['rms']:.2f} Hz/s RMS, "
            f"{retrospective['same_frequency_stream_difference_hz_s']['median_absolute']:.2f} Hz/s "
            "median absolute magnitude, and "
            f"{retrospective['same_frequency_stream_difference_hz_s']['p90_absolute']:.2f} Hz/s "
            "90th percentile. Existing dual-radio captures therefore cannot demonstrate the "
            "common-chain drift cancellation expected from a real single-radio hopper. This "
            "is not a calibrated hardware nuisance floor.",
            "",
            "## Prototype model",
            "",
            "For every retained CFO measurement, the replay jointly fits",
            "",
            "```text",
            "z = path_intercept + common_rate*t + edge_sign*differential_rate*t/2 + error",
            "edge_sign = -1 lower, +1 upper",
            "```",
            "",
            "so `differential_rate = upper_rate - lower_rate`. In these fixed-radio data, "
            "this is an edge-group slope contrast: physical RF scaling is confounded with "
            f"differential radio/LNB drift and path bias. All {phase_count} prespecified uniformly "
            "spaced phase offsets are evaluated. A measurement is retained only when its "
            "complete time interval lies "
            "after the two-frame guard and before the next retune boundary.",
            "",
            "The estimand is the best linear projection over the selected interval. Masking "
            "changes temporal weighting, so the reported deviation can include real Doppler "
            "curvature as well as information loss.",
            "",
            "![Virtual upper/lower switching analysis approach]"
            "(figures/2026_08_27_post_refill_edge_switching/edge-switching-approach.png)",
            "",
            "*Simultaneous fixed-edge products are conditionally masked onto a hypothetical "
            "single-radio schedule; actual retuning, settling, and reacquisition are absent.*",
            "",
            "![Switching hyperparameters and retained observations]"
            "(figures/2026_08_27_post_refill_edge_switching/edge-switching-data-retention.png)",
            "",
            "*The replay uses a two-frame guard, exact pilot-symbol support, "
            f"{phase_count} schedule "
            "phases, and a relative-UTC support envelope for the two-radio timing uncertainty.*",
            "",
            "### Coarse 20 ms GLRT observations",
            "",
            "| Dwell per edge | 103607 P90 deviation | 115401 P90 deviation | Interpretation |",
            "|---:|---:|---:|---|",
        ]
    )
    primary_coarse = {row["label"]: row for row in _schedule_lookup(primary, "coarse")}
    replication_coarse = {row["label"]: row for row in _schedule_lookup(replication, "coarse")}
    for label, dwell_s in SCHEDULES:
        p = primary_coarse[label]
        r = replication_coarse[label]
        if p["status"] != "complete" or r["status"] != "complete":
            p_value = r_value = "—"
            interpretation = "not resolvable: the measurement itself is too long"
        else:
            p_value = f"{p['absolute_masked_minus_unmasked_rate_deviation_p90_hz_s']:.2f} Hz/s"
            r_value = f"{r['absolute_masked_minus_unmasked_rate_deviation_p90_hz_s']:.2f} Hz/s"
            interpretation = "conditional product-availability replay"
        lines.append(f"| {dwell_s * 1000:.3f} ms | {r_value} | {p_value} | {interpretation} |")
    lines.extend(
        [
            "",
            "A 20 ms CFO probe cannot fit inside 12 ms. With a 2.667 ms guard, the "
            "22.667 ms schedule has zero start-time slack and is likewise not a meaningful "
            "coarse-product replay. The 42.667 ms schedule is the first nominal dwell that "
            "can contain the 20 ms product after the guard.",
            "",
            "The coarse replay is also oracle-conditioned: its branch and dealiased identity "
            "were selected using the complete recording before the schedule mask was applied.",
            "",
            "![Virtual-switching schedule-phase sensitivity]"
            "(figures/2026_08_27_post_refill_edge_switching/virtual-switching-sensitivity.png)",
            "",
            f"*P90 is the quantile over {phase_count} prespecified phase offsets of "
            "masked-minus-unmasked edge-group slope deviation for one selected event, not "
            "estimator accuracy or uncertainty.*",
            "",
            "### Fine receiver-local frame measurements (`115401`)",
            "",
            "The unmasked selected support is imbalanced: "
            f"{fine_baseline_edge_counts['lower']} lower-edge and "
            f"{fine_baseline_edge_counts['upper']} upper-edge observations. Per-edge retained "
            "fractions are therefore reported alongside the total.",
            "",
            "| Dwell per edge | Median retained | Lower / upper retained | "
            "Median absolute deviation | Nominal P90 deviation | "
            "P90 with relative-UTC support envelope |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in primary["fine"]["schedules"]:
        if row["status"] != "complete":
            continue
        timing_worst = fine_timing_by_label[row["label"]][
            "uncertainty_envelope_p90_masked_minus_unmasked_rate_deviation_hz_s"
        ]
        lines.append(
            f"| {row['dwell_s'] * 1000:.3f} ms | "
            f"{row['retained_observation_count_median']:.0f} "
            f"({100 * row['retained_fraction_median']:.1f}%) | "
            f"{100 * row['retained_lower_fraction_of_baseline_median']:.1f}% / "
            f"{100 * row['retained_upper_fraction_of_baseline_median']:.1f}% | "
            f"{row['absolute_masked_minus_unmasked_rate_deviation_median_hz_s']:.2f} "
            "Hz/s | "
            f"{row['absolute_masked_minus_unmasked_rate_deviation_p90_hz_s']:.2f} "
            "Hz/s | "
            f"{timing_worst:.2f} Hz/s |"
        )
    lines.extend(
        [
            "",
            f"The unmasked fine-product differential is "
            f"{primary['fine']['baseline']['differential_rate_hz_s']:.2f} Hz/s. "
            f"Its residual RMS is {primary['fine']['baseline']['residual_rms_hz']:.1f} Hz "
            f"and robust scale is {primary['fine']['baseline']['robust_scale_hz']:.1f} Hz. "
            "The replay uses raw per-frame `measurement_doppler_hz`, but only when the "
            f"persisted tracker accepted it and its absolute innovation is at most "
            f"{FRAME_INNOVATION_GATE_HZ:.0f} Hz. Because that gate and the trajectory were "
            "derived from the complete simultaneous recording, this is deliberately labeled "
            "an oracle-conditioned feasibility result.",
            "",
            "Each fine measurement is masked using the actual pilot support encoded by its "
            "frame sample index and Kalman pilot count (about 281.6 microseconds here), while "
            "the fit uses the persisted amplitude-weighted pilot-center timestamp.",
            "",
            "The final column expands every upper-edge support interval by "
            f"±{timing_sensitivity['upper_timing_uncertainty_ns'] / 1e6:.3f} ms, the manifest's "
            "declared cross-radio start-skew uncertainty, and then repeats the complete "
            f"{phase_count}-point phase sweep. A separate five-point relative timestamp "
            "shift is also "
            "summarized in the machine-readable results. Neither substitutes for a real "
            "shared counter.",
            "",
            "## What is and is not supported",
            "",
            "Supported now:",
            "",
            "- multi-second receiver/path-conditional edge-group slope fitting;",
            "- conditional time-multiplexing sensitivity estimates;",
            "- a preliminary 12 ms frame-product availability replay;",
            "- same-frequency controls for differential receiver drift.",
            "",
            "Not supported by these captures:",
            "",
            "- cross-radio sample or carrier-phase coherence;",
            "- decoded absolute Starlink frame identity or satellite identity;",
            "- actual Fast Lock settling/reacquisition behavior;",
            "- coherent 230.625 MHz synthetic-bandwidth TOA.",
            "",
            "The clean 3 MS/s `231207` capture is the best modern follow-up: it has complete "
            "device-axis native products and an exploratory four-path scaling event, but its "
            "sealed paired report explicitly disallows cross-radio association. The three "
            "5 MS/s captures must remain failed continuity evidence, not be silently repaired.",
            "",
            "## Next confirmatory step",
            "",
            "Freeze a branch/event using only a training interval, run the 12/22.667/42.667 ms "
            "masks on held-out frame measurements, and preregister an acceptable "
            "masked-minus-unmasked deviation. Then repeat on same-frequency controls. A "
            "bounded raw-IQ replay should then use the published V2/V3 recording reader to "
            "repeat branch selection, dealiasing, and measurement acceptance using retained "
            "samples only.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "PYTHONPATH=src .venv/bin/python tools/evaluate_post_refill_edge_switching.py",
            "PYTHONPATH=src .venv/bin/python tools/report_post_refill_edge_switching_figures.py",
            "```",
            "",
            f"Machine-readable results: [{output_path.name}]({output_link})",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = _arguments()
    results = build_results(
        bulk_root=args.bulk_root,
        recordings_root=args.recordings_root,
        retrospective_path=args.retrospective,
        verify_digest=not args.skip_digest_verification,
        phase_count=args.phase_count,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(args.report, results, args.output)


if __name__ == "__main__":
    main()
