#!/usr/bin/env python3
"""Replay the frozen recent-dwell CFO-tracker holdout protocol.

Every frozen capture interval is partitioned before looking at IQ into equal,
half-open tiles no longer than two seconds.  Each tile is independently bound
to an exact upstream GLRT source/epoch and is an independent tracker segment.
Only past even-Qin CFO estimates train a tracker; future odd-Qin estimates are
responses.  Results are first equalized over recording-anchored one-second
blocks and then over captures.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import hashlib
import io
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.research.adaptive_frame_cfo import (  # noqa: E402
    AdaptiveFrameCfoConfig,
    AdaptiveFrameCfoEstimate,
    AdaptiveFrameCfoPoint,
    AdaptiveFrameCfoTrack,
    track_adaptive_frame_cfo,
)
from leo.analysis.starlink.local_doppler import stable_measurement_floats  # noqa: E402
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402

try:  # noqa: E402
    import prototype_recent_frame_cfo_rate as frame_cfo_tool
except ModuleNotFoundError:  # pragma: no cover - imported from repository root
    from tools import prototype_recent_frame_cfo_rate as frame_cfo_tool

DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
DEFAULT_HOLDOUT_INPUTS = Path("config/analysis/recent-adaptive-cfo-holdout-v1.json")
DEFAULT_REPLAY_CONFIG = Path("config/analysis/recent-adaptive-cfo-holdout-replay-v1.json")
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_25_recent_adaptive_cfo_holdout")
DEFAULT_CHECKPOINT_ROOT = Path("reports/checkpoints/2026_08_25_recent_adaptive_cfo_holdout")
FROZEN_SELECTION_REFERENCE_UTC_NS = 1_787_676_193_000_000_000
FROZEN_MAXIMUM_AGE_S = 43_200.0
FROZEN_HOLDOUT_SHA256 = "sha256:547655cdf6a3bee84ae6877e2990083dad60d429b673b8d75e56b28d4e060dee"
QNAP_READ_ONLY_ROOT = Path("/mnt/qnap01")

METHOD_ADAPTIVE = "adaptive_75_500ms"
METHOD_FIXED_125 = "fixed_125ms"
METHOD_FIXED_500 = "fixed_500ms"
METHODS = (METHOD_FIXED_125, METHOD_FIXED_500, METHOD_ADAPTIVE)
_COLORS = {
    METHOD_FIXED_125: "#6b7280",
    METHOD_FIXED_500: "#2563eb",
    METHOD_ADAPTIVE: "#d97706",
}
_LABELS = {
    METHOD_FIXED_125: "Fixed 125 ms",
    METHOD_FIXED_500: "Fixed 500 ms",
    METHOD_ADAPTIVE: "Frozen adaptive",
}
_INVENTORY_FIELDS = {
    "continuity_safe",
    "even_absolute_cfo_hz",
    "frame_index",
    "frame_start_sample",
    "label",
    "odd_absolute_cfo_hz",
    "reference_time_s",
    "rejection_reasons",
    "training_supported",
}

# Tests patch this alias to prove that every tile performs a fresh raw replay
# and source/epoch binding.  Do not move binding out of ``_analyze_tile``.
_raw_analyze_dwell = frame_cfo_tool.analyze_dwell


@dataclass(frozen=True, slots=True)
class TileSpec:
    capture_label: str
    tile_id: str
    tile_index: int
    start_s: float
    stop_s: float


@dataclass(frozen=True, slots=True)
class TileReplay:
    tile: TileSpec
    frame_inventory: tuple[dict[str, object], ...]
    frame_epoch_sample: int
    source_id: str
    source_detection_time_s: float
    source_bound_cfo_hz: float
    opportunity_count: int


@dataclass(frozen=True, slots=True)
class Evaluation:
    forecasts: tuple[dict[str, object], ...]
    traces: tuple[dict[str, object], ...]
    summaries: tuple[dict[str, object], ...]
    coverage: tuple[dict[str, object], ...]
    comparison_effects: tuple[dict[str, object], ...]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_REPLAY_CONFIG)
    parser.add_argument("--holdout", type=Path, default=DEFAULT_HOLDOUT_INPUTS)
    parser.add_argument("--checkpoint-root", type=Path, default=DEFAULT_CHECKPOINT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--maximum-tiles",
        type=int,
        help="metadata/IQ smoke cap; requires a noncanonical output root",
    )
    return parser.parse_args()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _bytes_sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            stable_measurement_floats(value),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _validate_config(document: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "schema",
        "outcomes_opened_at_protocol_freeze",
        "holdout_input_sha256",
        "expected_labels",
        "maximum_tile_duration_s",
        "source_binding_radius_s",
        "profile_residual_half_width_hz",
        "profile_step_hz",
        "sample_rate_hz",
        "pilot_reference_offset_samples",
        "measurement_sigma_hz",
        "history_durations_ms",
        "fixed_history_durations_ms",
        "forecast_horizons_ms",
        "target_stride_frames",
        "aggregation_block_s",
        "maximum_gap_ms",
        "minimum_frames",
        "minimum_effective_frames",
        "minimum_history_coverage",
        "consistency_chi_square",
        "decision",
        "policies",
    }
    if set(document) != fields or document.get("schema") != (
        "org.leo.research.recent-adaptive-cfo-holdout-replay/v1"
    ):
        raise ValueError("unsupported or non-closed holdout replay configuration")
    if document["outcomes_opened_at_protocol_freeze"] is not False:
        raise ValueError("holdout replay was not frozen before outcomes were opened")
    digest = document["holdout_input_sha256"]
    if digest != FROZEN_HOLDOUT_SHA256:
        raise ValueError("holdout input digest changed after protocol freeze")
    labels = document["expected_labels"]
    if labels != [f"H{index}" for index in range(1, 8)]:
        raise ValueError("holdout labels must be the frozen H1-H7 cohort")

    frozen_scalars = {
        "maximum_tile_duration_s": 2.0,
        "source_binding_radius_s": 0.075,
        "profile_residual_half_width_hz": 2_000.0,
        "profile_step_hz": 20.0,
        "sample_rate_hz": 2_500_000,
        "pilot_reference_offset_samples": 1_672,
        "measurement_sigma_hz": 50.0,
        "target_stride_frames": 15,
        "aggregation_block_s": 1.0,
        "maximum_gap_ms": 100.0,
        "minimum_frames": 12,
        "minimum_effective_frames": 8,
        "minimum_history_coverage": 0.95,
        "consistency_chi_square": 9.210340371976184,
    }
    for name, expected in frozen_scalars.items():
        value = document[name]
        if isinstance(expected, int):
            valid = isinstance(value, int) and not isinstance(value, bool) and value == expected
        else:
            valid = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isclose(float(value), expected, rel_tol=0.0, abs_tol=1e-15)
            )
        if not valid:
            raise ValueError(f"holdout replay setting changed: {name}")
    if document["history_durations_ms"] != [75.0, 125.0, 250.0, 500.0]:
        raise ValueError("adaptive histories changed after protocol freeze")
    if document["fixed_history_durations_ms"] != [125.0, 500.0]:
        raise ValueError("fixed histories changed after protocol freeze")
    if document["forecast_horizons_ms"] != [125.0, 500.0, 1_000.0]:
        raise ValueError("forecast horizons changed after protocol freeze")

    decision = document["decision"]
    decision_fields = {
        "baseline_method",
        "challenger_method",
        "diagnostic_methods",
        "maximum_equal_capture_rms_ratio",
        "maximum_per_capture_rms_ratio",
        "minimum_paired_coverage",
        "minimum_nonempty_blocks_per_capture_horizon",
        "minimum_paired_targets_per_capture_horizon",
        "require_all_labels_at_all_horizons",
        "required_horizons_ms",
        "advance_on_pass",
        "effect_gate_failure_status",
        "provenance_or_support_failure_status",
    }
    if not isinstance(decision, dict) or set(decision) != decision_fields:
        raise ValueError("holdout decision contract is not closed")
    if (
        decision["baseline_method"] != METHOD_FIXED_125
        or decision["challenger_method"] != METHOD_FIXED_500
        or decision["diagnostic_methods"] != [METHOD_ADAPTIVE]
        or float(decision["maximum_equal_capture_rms_ratio"]) != 0.9
        or float(decision["maximum_per_capture_rms_ratio"]) != 1.05
        or float(decision["minimum_paired_coverage"]) != 0.9
        or int(decision["minimum_nonempty_blocks_per_capture_horizon"]) != 5
        or int(decision["minimum_paired_targets_per_capture_horizon"]) != 100
        or decision["require_all_labels_at_all_horizons"] is not True
        or decision["required_horizons_ms"] != [125.0, 500.0, 1_000.0]
        or decision["effect_gate_failure_status"] != "scientific_fail"
        or decision["provenance_or_support_failure_status"] != "inconclusive"
    ):
        raise ValueError("holdout decision thresholds changed after protocol freeze")
    policies = document["policies"]
    required_policies = {
        "tile_geometry",
        "epoch",
        "continuity",
        "tracker_reset",
        "scoring_core",
        "training",
        "response",
        "aggregation",
        "interpretation",
    }
    if (
        not isinstance(policies, dict)
        or set(policies) != required_policies
        or any(not isinstance(value, str) or not value for value in policies.values())
    ):
        raise ValueError("holdout replay policies are not closed")
    return document


_HOLDOUT_FIELDS = {
    "schema",
    "selection_reference_utc_ns",
    "maximum_age_s",
    "selection_basis",
    "frame_cfo_outcomes_examined_at_freeze",
    "required_replay_policy",
    "dwells",
}
_DWELL_FIELDS = {
    "label",
    "session_id",
    "run_id",
    "scope_id",
    "stream_id",
    "radio_id",
    "receiver_id",
    "edge",
    "branch_id",
    "trajectory_id",
    "analysis_start_s",
    "analysis_stop_s",
    "recording_manifest_sha256",
    "analysis_manifest_sha256",
    "pilot_scan_sha256",
    "dealiased_bank_sha256",
    "final_bank_sha256",
}


def _validate_holdout(
    document: dict[str, Any], config: dict[str, Any]
) -> tuple[dict[str, Any], ...]:
    if set(document) != _HOLDOUT_FIELDS or document.get("schema") != (
        "org.leo.research.recent-adaptive-cfo-holdout/v1"
    ):
        raise ValueError("unsupported or non-closed frozen holdout input")
    if document["frame_cfo_outcomes_examined_at_freeze"] is not False:
        raise ValueError("holdout outcomes were opened before the frozen selection")
    reference = document["selection_reference_utc_ns"]
    maximum_age = document["maximum_age_s"]
    if (
        not isinstance(reference, int)
        or isinstance(reference, bool)
        or reference <= 0
        or not isinstance(maximum_age, (int, float))
        or isinstance(maximum_age, bool)
        or float(maximum_age) != 43_200.0
    ):
        raise ValueError("holdout recency contract is invalid")
    dwells = document["dwells"]
    if not isinstance(dwells, list) or len(dwells) != 7:
        raise ValueError("holdout must contain exactly seven captures")
    output: list[dict[str, Any]] = []
    for raw in dwells:
        if not isinstance(raw, dict) or set(raw) != _DWELL_FIELDS:
            raise ValueError("holdout dwell fields are not closed")
        item = dict(raw)
        start_s = item["analysis_start_s"]
        stop_s = item["analysis_stop_s"]
        if (
            not isinstance(start_s, (int, float))
            or not isinstance(stop_s, (int, float))
            or not math.isfinite(float(start_s))
            or not math.isfinite(float(stop_s))
            or not 0.0 <= float(start_s) < float(stop_s) <= 60.0
            or float(stop_s) - float(start_s) < 10.0
        ):
            raise ValueError("holdout dwell interval is invalid")
        output.append(item)
    labels = [str(item["label"]) for item in output]
    if labels != list(config["expected_labels"]):
        raise ValueError("holdout labels disagree with replay protocol")
    if len({str(item["session_id"]) for item in output}) != len(output):
        raise ValueError("holdout captures must be independent sessions")
    return tuple(output)


def _load_holdout(path: Path, config: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Load the frozen cohort only when its byte digest and identities still match."""

    if _sha256(path) != config["holdout_input_sha256"]:
        raise ValueError("frozen holdout input digest mismatch")
    document = _load_object(path)
    if document.get("selection_reference_utc_ns") != FROZEN_SELECTION_REFERENCE_UTC_NS:
        raise ValueError("frozen holdout selection reference changed")
    if float(document.get("maximum_age_s", math.nan)) != FROZEN_MAXIMUM_AGE_S:
        raise ValueError("frozen holdout maximum age changed")
    return _validate_holdout(document, config)


def _plan_tiles(item: dict[str, Any], maximum_tile_duration_s: float) -> tuple[TileSpec, ...]:
    """Return metadata-only equal-width half-open tiles for one frozen interval."""

    start_s = float(item["analysis_start_s"])
    stop_s = float(item["analysis_stop_s"])
    if (
        not math.isfinite(maximum_tile_duration_s)
        or maximum_tile_duration_s <= 0.0
        or not 0.0 <= start_s < stop_s
    ):
        raise ValueError("tile geometry is invalid")
    span_s = stop_s - start_s
    tile_count = max(1, math.ceil(span_s / maximum_tile_duration_s - 1e-12))
    boundaries = [start_s + span_s * index / tile_count for index in range(tile_count + 1)]
    boundaries[0] = start_s
    boundaries[-1] = stop_s
    label = str(item["label"])
    tiles = tuple(
        TileSpec(
            capture_label=label,
            tile_id=f"{label}-T{index:03d}",
            tile_index=index,
            start_s=boundaries[index],
            stop_s=boundaries[index + 1],
        )
        for index in range(tile_count)
    )
    widths = np.asarray([tile.stop_s - tile.start_s for tile in tiles], dtype=float)
    minimum_scored_width_s = 1.5
    if (
        np.max(widths) > maximum_tile_duration_s + 1e-12
        or np.min(widths) + 1e-12 < minimum_scored_width_s
        or np.max(widths) - np.min(widths) > 1e-12
        or any(left.stop_s != right.start_s for left, right in zip(tiles, tiles[1:], strict=False))
    ):
        raise ValueError("tile planner failed its equal-width coverage contract")
    return tiles


def _analyze_tile(
    store: RecordingStore,
    bulk_root: Path,
    item: dict[str, Any],
    tile: TileSpec,
    config: dict[str, Any],
) -> TileReplay:
    """Analyze one tile with a fresh invocation of upstream GLRT epoch binding."""

    if tile.capture_label != item["label"]:
        raise ValueError("tile capture identity disagrees with frozen dwell")
    tile_item = dict(item)
    tile_item.update(
        {
            "label": tile.tile_id,
            "analysis_start_s": tile.start_s,
            "analysis_stop_s": tile.stop_s,
        }
    )
    raw_document = {
        "selection_reference_utc_ns": FROZEN_SELECTION_REFERENCE_UTC_NS,
        "maximum_age_s": FROZEN_MAXIMUM_AGE_S,
        "profile_residual_half_width_hz": config["profile_residual_half_width_hz"],
        "profile_step_hz": config["profile_step_hz"],
    }
    bound = _raw_analyze_dwell(
        store,
        bulk_root,
        tile_item,
        raw_document,
        maximum_frames=None,
    )
    radius_s = float(config["source_binding_radius_s"])
    midpoint_s = 0.5 * (tile.start_s + tile.stop_s)
    if abs(float(bound.source.detection_time_s) - midpoint_s) > radius_s + 1e-12:
        raise ValueError("tile source lies outside the frozen midpoint binding radius")
    inventory = tuple(dict(row) for row in bound.frame_inventory)
    if not inventory or any(row.get("label") != tile.tile_id for row in inventory):
        raise ValueError("tile frame inventory identity is invalid")
    return TileReplay(
        tile=tile,
        frame_inventory=inventory,
        frame_epoch_sample=int(bound.frame_epoch_sample),
        source_id=str(bound.source.source_id),
        source_detection_time_s=float(bound.source.detection_time_s),
        source_bound_cfo_hz=float(bound.source_bound_cfo_hz),
        opportunity_count=int(bound.opportunity_count),
    )


def _item_digest(item: dict[str, Any]) -> str:
    return _bytes_sha256(_json_bytes(item))


def _checkpoint_contract(
    item: dict[str, Any], tile: TileSpec, config: dict[str, Any]
) -> dict[str, object]:
    protocol = {key: value for key, value in config.items() if not str(key).startswith("_")}
    return {
        "holdout_input_sha256": config["holdout_input_sha256"],
        "replay_config_sha256": str(
            config.get("_replay_config_sha256", _bytes_sha256(_json_bytes(protocol)))
        ),
        "frozen_dwell_sha256": _item_digest(item),
        "implementation_sha256": {
            "tool": _sha256(Path(__file__)),
            "raw_frame_cfo_tool": _sha256(Path(frame_cfo_tool.__file__)),
            "frame_profile": _sha256(Path(__file__).parents[1] / "src/leo/analysis/qam/pilot.py"),
            "adaptive_tracker": _sha256(
                Path(__file__).parents[1] / "src/leo/analysis/research/adaptive_frame_cfo.py"
            ),
        },
        "tile": asdict(tile),
    }


def _checkpoint_path(checkpoint_root: Path, tile: TileSpec) -> Path:
    return checkpoint_root / f"{tile.tile_id}.json"


def _checkpoint_payload(
    replay: TileReplay,
    item: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, object]:
    body: dict[str, object] = {
        "schema": "org.leo.research.recent-adaptive-cfo-tile-replay/v1",
        "contract": _checkpoint_contract(item, replay.tile, config),
        "frame_epoch_sample": replay.frame_epoch_sample,
        "source_id": replay.source_id,
        "source_detection_time_s": replay.source_detection_time_s,
        "source_bound_cfo_hz": replay.source_bound_cfo_hz,
        "opportunity_count": replay.opportunity_count,
        "frame_inventory": list(replay.frame_inventory),
    }
    body_bytes = _json_bytes(body)
    return {
        "schema": "org.leo.research.recent-adaptive-cfo-tile-checkpoint/v1",
        "payload_sha256": _bytes_sha256(body_bytes),
        "payload": body,
    }


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _validate_write_roots(checkpoint_root: Path, output_root: Path) -> None:
    """Keep generated artifacts separate and outside the read-only QNAP tree."""

    checkpoint = checkpoint_root.resolve()
    output = output_root.resolve()
    qnap = QNAP_READ_ONLY_ROOT.resolve()
    if checkpoint == output:
        raise ValueError("checkpoint and output roots must be distinct")
    for name, path in (("checkpoint", checkpoint), ("output", output)):
        if path == qnap or qnap in path.parents:
            raise ValueError(f"{name} root cannot be beneath read-only /mnt/qnap01")


def _validate_inventory(
    raw: object,
    tile: TileSpec,
) -> tuple[dict[str, object], ...]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("tile checkpoint frame inventory must be nonempty")
    output: list[dict[str, object]] = []
    identities: set[int] = set()
    previous_time = -math.inf
    for row in raw:
        if not isinstance(row, dict) or set(row) != _INVENTORY_FIELDS:
            raise ValueError("tile frame inventory row is not closed")
        frame_start = row["frame_start_sample"]
        frame_index = row["frame_index"]
        reference_time_s = row["reference_time_s"]
        if (
            row["label"] != tile.tile_id
            or isinstance(frame_start, bool)
            or not isinstance(frame_start, int)
            or frame_start < 0
            or frame_start in identities
            or isinstance(frame_index, bool)
            or not isinstance(frame_index, int)
            or frame_index < 0
            or isinstance(reference_time_s, bool)
            or not isinstance(reference_time_s, (int, float))
            or not math.isfinite(float(reference_time_s))
            or float(reference_time_s) <= previous_time
            or not tile.start_s <= float(reference_time_s) < tile.stop_s
        ):
            raise ValueError("tile frame identity or time is invalid")
        if not isinstance(row["continuity_safe"], bool) or not isinstance(
            row["training_supported"], bool
        ):
            raise ValueError("tile support flags must be Boolean")
        if not isinstance(row["rejection_reasons"], list) or any(
            not isinstance(reason, str) for reason in row["rejection_reasons"]
        ):
            raise ValueError("tile rejection reasons are invalid")
        even_value = row["even_absolute_cfo_hz"]
        odd_value = row["odd_absolute_cfo_hz"]
        if bool(row["training_supported"]) and (
            isinstance(even_value, bool)
            or not isinstance(even_value, (int, float))
            or not math.isfinite(float(even_value))
        ):
            raise ValueError("supported tile training CFO is invalid")
        for name, value in (
            ("even", even_value),
            ("odd", odd_value),
        ):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise ValueError(f"tile {name} split-CFO value is invalid")
        identities.add(frame_start)
        previous_time = float(reference_time_s)
        output.append(dict(row))
    return tuple(output)


def _replay_from_checkpoint(
    document: dict[str, Any],
    item: dict[str, Any],
    tile: TileSpec,
    config: dict[str, Any],
) -> TileReplay:
    if (
        set(document) != {"schema", "payload_sha256", "payload"}
        or document.get("schema") != "org.leo.research.recent-adaptive-cfo-tile-checkpoint/v1"
    ):
        raise ValueError("tile checkpoint envelope is not closed")
    body = document["payload"]
    if not isinstance(body, dict) or _bytes_sha256(_json_bytes(body)) != document["payload_sha256"]:
        raise ValueError("tile checkpoint payload digest mismatch")
    body_fields = {
        "schema",
        "contract",
        "frame_epoch_sample",
        "source_id",
        "source_detection_time_s",
        "source_bound_cfo_hz",
        "opportunity_count",
        "frame_inventory",
    }
    if set(body) != body_fields or body.get("schema") != (
        "org.leo.research.recent-adaptive-cfo-tile-replay/v1"
    ):
        raise ValueError("tile checkpoint payload is not closed")
    expected_contract = stable_measurement_floats(_checkpoint_contract(item, tile, config))
    if body["contract"] != expected_contract:
        raise ValueError("tile checkpoint identity, inputs, or implementation changed")
    scalar_ints = (body["frame_epoch_sample"], body["opportunity_count"])
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in scalar_ints
    ):
        raise ValueError("tile checkpoint counts are invalid")
    if not isinstance(body["source_id"], str) or not body["source_id"]:
        raise ValueError("tile checkpoint source identity is invalid")
    for name in ("source_detection_time_s", "source_bound_cfo_hz"):
        value = body[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ValueError("tile checkpoint source value is invalid")
    midpoint_s = 0.5 * (tile.start_s + tile.stop_s)
    if (
        abs(float(body["source_detection_time_s"]) - midpoint_s)
        > float(config["source_binding_radius_s"]) + 1e-12
    ):
        raise ValueError("checkpoint source is outside the frozen binding radius")
    inventory = _validate_inventory(body["frame_inventory"], tile)
    if int(body["opportunity_count"]) != len(inventory):
        raise ValueError("checkpoint opportunity count disagrees with its inventory")
    return TileReplay(
        tile=tile,
        frame_inventory=inventory,
        frame_epoch_sample=int(body["frame_epoch_sample"]),
        source_id=str(body["source_id"]),
        source_detection_time_s=float(body["source_detection_time_s"]),
        source_bound_cfo_hz=float(body["source_bound_cfo_hz"]),
        opportunity_count=int(body["opportunity_count"]),
    )


def _load_or_analyze_tile(
    checkpoint_root: Path,
    store: RecordingStore,
    bulk_root: Path,
    item: dict[str, Any],
    tile: TileSpec,
    config: dict[str, Any],
) -> TileReplay:
    """Resume only an exact verified tile; otherwise replay it once and checkpoint."""

    path = _checkpoint_path(checkpoint_root, tile)
    if path.exists():
        raw = path.read_bytes()
        document = json.loads(raw)
        if not isinstance(document, dict) or raw != _json_bytes(document):
            raise ValueError("tile checkpoint bytes are not canonical")
        return _replay_from_checkpoint(document, item, tile, config)
    replay = _analyze_tile(store, bulk_root, item, tile, config)
    if replay.tile != tile:
        raise ValueError("raw tile replay returned the wrong tile identity")
    document = _checkpoint_payload(replay, item, config)
    payload = _json_bytes(document)
    canonical_document = json.loads(payload)
    if not isinstance(canonical_document, dict):
        raise ValueError("canonical tile checkpoint is not an object")
    canonical = _replay_from_checkpoint(canonical_document, item, tile, config)
    _atomic_write(path, payload)
    return canonical


def _tracker_config(
    config: dict[str, Any], histories_ms: tuple[float, ...]
) -> AdaptiveFrameCfoConfig:
    return AdaptiveFrameCfoConfig(
        history_durations_s=tuple(value / 1_000.0 for value in histories_ms),
        minimum_history_coverage=float(config["minimum_history_coverage"]),
        minimum_frames=int(config["minimum_frames"]),
        minimum_effective_frames=float(config["minimum_effective_frames"]),
        maximum_gap_s=float(config["maximum_gap_ms"]) / 1_000.0,
        consistency_chi_square=float(config["consistency_chi_square"]),
    )


def _prepared_rows(
    replays: tuple[TileReplay, ...],
) -> dict[str, tuple[dict[str, object], ...]]:
    """Attach a capture-global, outcome-independent opportunity rank to each row."""

    grouped: dict[str, list[tuple[TileSpec, dict[str, object]]]] = defaultdict(list)
    tile_ids: set[str] = set()
    for replay in replays:
        if replay.tile.tile_id in tile_ids:
            raise ValueError("tile replays must have unique identities")
        tile_ids.add(replay.tile.tile_id)
        for row in replay.frame_inventory:
            grouped[replay.tile.capture_label].append((replay.tile, row))
    output: dict[str, tuple[dict[str, object], ...]] = {}
    for label, selected in grouped.items():
        selected.sort(
            key=lambda pair: (
                float(pair[1]["reference_time_s"]),
                int(pair[1]["frame_start_sample"]),
                pair[0].tile_index,
            )
        )
        seen_samples: set[int] = set()
        rows: list[dict[str, object]] = []
        for capture_frame_index, (tile, raw) in enumerate(selected):
            frame_start = int(raw["frame_start_sample"])
            if frame_start in seen_samples:
                raise ValueError("tile inventories overlap in device samples")
            seen_samples.add(frame_start)
            row = dict(raw)
            row.update(
                {
                    "capture_label": label,
                    "tile_id": tile.tile_id,
                    "tile_index": tile.tile_index,
                    "capture_frame_index": capture_frame_index,
                }
            )
            rows.append(row)
        output[label] = tuple(rows)
    return output


def _tile_rows(
    replay: TileReplay,
    prepared: dict[str, tuple[dict[str, object], ...]],
) -> tuple[dict[str, object], ...]:
    rows = tuple(
        row for row in prepared[replay.tile.capture_label] if row["tile_id"] == replay.tile.tile_id
    )
    if len(rows) != len(replay.frame_inventory):
        raise ValueError("prepared tile inventory lost frame opportunities")
    return rows


def _build_tile_tracks(
    rows: tuple[dict[str, object], ...], config: dict[str, Any]
) -> dict[str, AdaptiveFrameCfoTrack]:
    sigma_hz = float(config["measurement_sigma_hz"])
    selected: list[tuple[dict[str, object], int]] = []
    continuity_segment = 0
    unsafe_since_last_point = False
    for row in rows:
        if not bool(row["continuity_safe"]):
            unsafe_since_last_point = True
            continue
        if unsafe_since_last_point:
            continuity_segment += 1
            unsafe_since_last_point = False
        if bool(row["training_supported"]):
            selected.append((row, continuity_segment))
    points = tuple(
        AdaptiveFrameCfoPoint(
            frame_start_sample=int(row["frame_start_sample"]),
            reference_time_s=float(row["reference_time_s"]),
            continuity_segment=segment,
            even_cfo_hz=float(row["even_absolute_cfo_hz"]),
            even_cfo_sigma_hz=sigma_hz,
        )
        for row, segment in selected
    )
    histories = tuple(float(value) for value in config["history_durations_ms"])
    return {
        METHOD_FIXED_125: track_adaptive_frame_cfo(
            points, config=_tracker_config(config, (125.0,))
        ),
        METHOD_FIXED_500: track_adaptive_frame_cfo(
            points, config=_tracker_config(config, (500.0,))
        ),
        METHOD_ADAPTIVE: track_adaptive_frame_cfo(
            points, config=_tracker_config(config, histories)
        ),
    }


def _estimate_map(track: AdaptiveFrameCfoTrack) -> dict[int, AdaptiveFrameCfoEstimate]:
    return {estimate.frame_start_sample: estimate for estimate in track.estimates}


def _locklet_map(track: AdaptiveFrameCfoTrack) -> tuple[dict[int, int], dict[int, float]]:
    locklet = -1
    identities: dict[int, int] = {}
    starts: dict[int, float] = {}
    for estimate in track.estimates:
        if estimate.reset_reason.value != "none":
            locklet += 1
            starts[locklet] = estimate.reference_time_s
        identities[estimate.frame_start_sample] = locklet
    return identities, starts


def _forecast_tile(
    replay: TileReplay,
    rows: tuple[dict[str, object], ...],
    tracks: dict[str, AdaptiveFrameCfoTrack],
    config: dict[str, Any],
) -> tuple[tuple[dict[str, object], ...], set[tuple[str, float, int]]]:
    """Return paired forecasts plus the even-only eligible target identities."""

    sample_rate_hz = int(config["sample_rate_hz"])
    reference_offset = int(config["pilot_reference_offset_samples"])
    stride = int(config["target_stride_frames"])
    block_s = float(config["aggregation_block_s"])
    minimum_history_s = (
        max(float(value) for value in config["history_durations_ms"])
        * float(config["minimum_history_coverage"])
        / 1_000.0
    )
    training = tuple(
        row for row in rows if bool(row["continuity_safe"]) and bool(row["training_supported"])
    )
    training_reference_samples = [
        int(row["frame_start_sample"]) + reference_offset for row in training
    ]
    maps = {method: _estimate_map(track) for method, track in tracks.items()}
    locklets, locklet_starts = _locklet_map(tracks[METHOD_ADAPTIVE])
    targets = tuple(row for row in training if int(row["capture_frame_index"]) % stride == 0)
    output: list[dict[str, object]] = []
    eligible: set[tuple[str, float, int]] = set()
    for target in targets:
        target_frame_start = int(target["frame_start_sample"])
        target_reference_sample = target_frame_start + reference_offset
        for raw_horizon_ms in config["forecast_horizons_ms"]:
            horizon_ms = float(raw_horizon_ms)
            horizon_samples = round(horizon_ms * sample_rate_hz / 1_000.0)
            requested_cutoff_sample = target_reference_sample - horizon_samples
            index = bisect.bisect_right(training_reference_samples, requested_cutoff_sample) - 1
            if index < 0:
                continue
            cutoff = training[index]
            cutoff_frame_start = int(cutoff["frame_start_sample"])
            target_locklet = locklets.get(target_frame_start)
            cutoff_locklet = locklets.get(cutoff_frame_start)
            if target_locklet is None or cutoff_locklet != target_locklet:
                continue
            cutoff_time_s = float(cutoff["reference_time_s"])
            if cutoff_time_s - locklet_starts[target_locklet] + 1e-12 < minimum_history_s:
                continue
            eligibility_id = (replay.tile.capture_label, horizon_ms, target_frame_start)
            eligible.add(eligibility_id)
            odd_response = target["odd_absolute_cfo_hz"]
            if odd_response is None:
                continue
            estimates = {method: maps[method].get(cutoff_frame_start) for method in METHODS}
            if any(
                estimate is None
                or estimate.cfo_hz is None
                or estimate.rate_hz_s is None
                or estimate.cfo_sigma_hz is None
                or estimate.rate_sigma_hz_s is None
                or estimate.cfo_rate_covariance_hz2_s is None
                for estimate in estimates.values()
            ):
                continue
            training_stop_reference_sample = cutoff_frame_start + reference_offset
            delta_s = (target_reference_sample - training_stop_reference_sample) / sample_rate_hz
            pair_id = (
                f"{replay.tile.capture_label}:{replay.tile.tile_id}:"
                f"{target_frame_start}:{horizon_samples}samples"
            )
            for method in METHODS:
                estimate = estimates[method]
                assert estimate is not None
                assert estimate.cfo_hz is not None
                assert estimate.rate_hz_s is not None
                assert estimate.cfo_sigma_hz is not None
                assert estimate.rate_sigma_hz_s is not None
                assert estimate.cfo_rate_covariance_hz2_s is not None
                prediction_hz = estimate.cfo_hz + estimate.rate_hz_s * delta_s
                variance_hz2 = (
                    estimate.cfo_sigma_hz**2
                    + delta_s**2 * estimate.rate_sigma_hz_s**2
                    + 2.0 * delta_s * estimate.cfo_rate_covariance_hz2_s
                )
                target_odd_hz = float(odd_response)
                output.append(
                    {
                        "pair_id": pair_id,
                        "capture_label": replay.tile.capture_label,
                        "tile_id": replay.tile.tile_id,
                        "training_tile_id": replay.tile.tile_id,
                        "method": method,
                        "horizon_ms": horizon_ms,
                        "block_index": math.floor(
                            target_reference_sample / (sample_rate_hz * block_s)
                        ),
                        "capture_frame_index": int(target["capture_frame_index"]),
                        "target_frame_start_sample": target_frame_start,
                        "target_reference_sample": target_reference_sample,
                        "target_time_s": float(target["reference_time_s"]),
                        "target_odd_cfo_hz": target_odd_hz,
                        "cutoff_sample": requested_cutoff_sample,
                        "training_cutoff_frame_start_sample": cutoff_frame_start,
                        "training_stop_reference_sample": training_stop_reference_sample,
                        "training_stop_time_s": estimate.reference_time_s,
                        "actual_forecast_s": delta_s,
                        "selected_history_ms": float(estimate.selected_history_s) * 1_000.0,
                        "cfo_hz_at_cutoff": estimate.cfo_hz,
                        "rate_hz_s": estimate.rate_hz_s,
                        "prediction_hz": prediction_hz,
                        "prediction_sigma_hz": math.sqrt(max(variance_hz2, 0.0)),
                        "odd_residual_hz": target_odd_hz - prediction_hz,
                    }
                )
    return tuple(output), eligible


def _validate_paired_rows(rows: tuple[dict[str, object], ...]) -> None:
    methods_by_pair: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        methods_by_pair[str(row["pair_id"])].add(str(row["method"]))
        if int(row["training_stop_reference_sample"]) > int(row["cutoff_sample"]):
            raise ValueError("forecast training cutoff uses a future frame")
    if rows and any(methods != set(METHODS) for methods in methods_by_pair.values()):
        raise ValueError("forecast methods do not share one paired target mask")


def _rate_traces(
    replay: TileReplay,
    rows: tuple[dict[str, object], ...],
    tracks: dict[str, AdaptiveFrameCfoTrack],
    config: dict[str, Any],
) -> tuple[dict[str, object], ...]:
    row_by_sample = {int(row["frame_start_sample"]): row for row in rows}
    stride = int(config["target_stride_frames"])
    output: list[dict[str, object]] = []
    for method in METHODS:
        for estimate in tracks[method].estimates:
            row = row_by_sample[estimate.frame_start_sample]
            if int(row["capture_frame_index"]) % stride or estimate.rate_hz_s is None:
                continue
            output.append(
                {
                    "capture_label": replay.tile.capture_label,
                    "tile_id": replay.tile.tile_id,
                    "tracker_segment_id": replay.tile.tile_id,
                    "method": method,
                    "frame_start_sample": estimate.frame_start_sample,
                    "reference_time_s": estimate.reference_time_s,
                    "selected_history_ms": float(estimate.selected_history_s) * 1_000.0,
                    "cfo_hz": estimate.cfo_hz,
                    "rate_hz_s": estimate.rate_hz_s,
                    "rate_sigma_hz_s": estimate.rate_sigma_hz_s,
                    "reset_reason": estimate.reset_reason.value,
                    "selection_reason": estimate.selection_reason.value,
                    "history_change_reason": estimate.history_change_reason.value,
                }
            )
    return tuple(output)


def _summaries(rows: tuple[dict[str, object], ...]) -> tuple[dict[str, object], ...]:
    _validate_paired_rows(rows)
    groups: dict[tuple[str, float, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[
            (
                str(row["capture_label"]),
                float(row["horizon_ms"]),
                str(row["method"]),
            )
        ].append(row)
    output: list[dict[str, object]] = []
    capture_mse: dict[tuple[float, str], list[float]] = defaultdict(list)
    for (label, horizon_ms, method), selected in sorted(groups.items()):
        residual = np.asarray([float(row["odd_residual_hz"]) for row in selected])
        blocks: dict[int, list[float]] = defaultdict(list)
        for row in selected:
            blocks[int(row["block_index"])].append(float(row["odd_residual_hz"]) ** 2)
        block_mse = [float(np.mean(values)) for _, values in sorted(blocks.items())]
        equal_block_mse = float(np.mean(block_mse))
        capture_mse[(horizon_ms, method)].append(equal_block_mse)
        output.append(
            {
                "scope": "capture",
                "label": label,
                "horizon_ms": horizon_ms,
                "method": method,
                "target_count": len(selected),
                "tile_count": len({str(row["tile_id"]) for row in selected}),
                "block_count": len(blocks),
                "odd_rms_hz": math.sqrt(float(np.mean(residual**2))),
                "odd_block_equal_rms_hz": math.sqrt(equal_block_mse),
                "odd_median_absolute_hz": float(np.median(np.abs(residual))),
                "odd_bias_hz": float(np.mean(residual)),
            }
        )
    for (horizon_ms, method), values in sorted(capture_mse.items()):
        output.append(
            {
                "scope": "equal_capture",
                "label": "ALL",
                "horizon_ms": horizon_ms,
                "method": method,
                "capture_count": len(values),
                "odd_block_capture_equal_rms_hz": math.sqrt(float(np.mean(values))),
            }
        )
    return tuple(output)


def _summary_lookup(
    summaries: tuple[dict[str, object], ...],
    scope: str,
    label: str,
    horizon_ms: float,
    method: str,
) -> dict[str, object]:
    matches = [
        row
        for row in summaries
        if row["scope"] == scope
        and row["label"] == label
        and float(row["horizon_ms"]) == horizon_ms
        and row["method"] == method
    ]
    if len(matches) != 1:
        raise ValueError("holdout summary lookup is not unique")
    return matches[0]


def _comparison_effects(
    summaries: tuple[dict[str, object], ...], config: dict[str, Any]
) -> tuple[dict[str, object], ...]:
    output: list[dict[str, object]] = []
    labels = tuple(str(value) for value in config["expected_labels"])
    for horizon in tuple(float(value) for value in config["forecast_horizons_ms"]):
        for candidate in (METHOD_FIXED_500, METHOD_ADAPTIVE):
            per_capture: dict[str, float] = {}
            for label in labels:
                baseline = float(
                    _summary_lookup(summaries, "capture", label, horizon, METHOD_FIXED_125)[
                        "odd_block_equal_rms_hz"
                    ]
                )
                value = float(
                    _summary_lookup(summaries, "capture", label, horizon, candidate)[
                        "odd_block_equal_rms_hz"
                    ]
                )
                per_capture[label] = value / baseline
            aggregate_baseline = float(
                _summary_lookup(summaries, "equal_capture", "ALL", horizon, METHOD_FIXED_125)[
                    "odd_block_capture_equal_rms_hz"
                ]
            )
            aggregate_value = float(
                _summary_lookup(summaries, "equal_capture", "ALL", horizon, candidate)[
                    "odd_block_capture_equal_rms_hz"
                ]
            )
            output.append(
                {
                    "horizon_ms": horizon,
                    "candidate_method": candidate,
                    "baseline_method": METHOD_FIXED_125,
                    "equal_capture_rms_ratio": aggregate_value / aggregate_baseline,
                    "equal_capture_rms_change_percent": 100.0
                    * (1.0 - aggregate_value / aggregate_baseline),
                    "worst_capture_ratio": max(per_capture.values()),
                    "per_capture_ratio": per_capture,
                }
            )
    return tuple(output)


def _coverage_rows(
    forecasts: tuple[dict[str, object], ...],
    eligible: set[tuple[str, float, int]],
    config: dict[str, Any],
) -> tuple[dict[str, object], ...]:
    paired = {
        (
            str(row["capture_label"]),
            float(row["horizon_ms"]),
            int(row["target_frame_start_sample"]),
        )
        for row in forecasts
    }
    output: list[dict[str, object]] = []
    for label in tuple(str(value) for value in config["expected_labels"]):
        for horizon_ms in tuple(float(value) for value in config["forecast_horizons_ms"]):
            identities = {
                identity
                for identity in eligible
                if identity[0] == label and identity[1] == horizon_ms
            }
            predicted = len(identities & paired)
            blocks = {
                int(row["block_index"])
                for row in forecasts
                if row["capture_label"] == label
                and float(row["horizon_ms"]) == horizon_ms
                and row["method"] == METHOD_FIXED_125
            }
            output.append(
                {
                    "label": label,
                    "capture_label": label,
                    "horizon_ms": horizon_ms,
                    "eligible_target_count": len(identities),
                    "paired_prediction_count": predicted,
                    "paired_coverage": predicted / len(identities) if identities else 0.0,
                    "nonempty_block_count": len(blocks),
                }
            )
    return tuple(output)


def _evaluate_tiles(replays: tuple[TileReplay, ...], config: dict[str, Any]) -> Evaluation:
    prepared = _prepared_rows(replays)
    forecasts: list[dict[str, object]] = []
    traces: list[dict[str, object]] = []
    eligible: set[tuple[str, float, int]] = set()
    for replay in sorted(
        replays,
        key=lambda value: (value.tile.capture_label, value.tile.tile_index),
    ):
        rows = _tile_rows(replay, prepared)
        tracks = _build_tile_tracks(rows, config)
        tile_forecasts, tile_eligible = _forecast_tile(replay, rows, tracks, config)
        forecasts.extend(tile_forecasts)
        eligible.update(tile_eligible)
        traces.extend(_rate_traces(replay, rows, tracks, config))
    ordered_forecasts = tuple(
        sorted(
            forecasts,
            key=lambda row: (
                str(row["capture_label"]),
                float(row["horizon_ms"]),
                int(row["target_frame_start_sample"]),
                METHODS.index(str(row["method"])),
            ),
        )
    )
    _validate_paired_rows(ordered_forecasts)
    ordered_traces = tuple(
        sorted(
            traces,
            key=lambda row: (
                str(row["capture_label"]),
                float(row["reference_time_s"]),
                METHODS.index(str(row["method"])),
            ),
        )
    )
    summaries = _summaries(ordered_forecasts)
    coverage = _coverage_rows(ordered_forecasts, eligible, config)
    try:
        effects = _comparison_effects(summaries, config) if ordered_forecasts else ()
    except ValueError:
        # Missing capture/horizon summaries are a predeclared support failure,
        # reported as inconclusive by ``_decision_status`` rather than a crash.
        effects = ()
    return Evaluation(
        forecasts=ordered_forecasts,
        traces=ordered_traces,
        summaries=summaries,
        coverage=coverage,
        comparison_effects=effects,
    )


def _decision_status(
    summaries: tuple[dict[str, object], ...],
    coverage: tuple[dict[str, object], ...],
    config: dict[str, Any],
) -> dict[str, object]:
    """Apply the frozen support gates before the frozen fixed-500 effect gates."""

    decision = config["decision"]
    labels = tuple(str(value) for value in config["expected_labels"])
    horizons = tuple(float(value) for value in decision["required_horizons_ms"])
    support_failures: list[str] = []
    coverage_results: list[dict[str, object]] = []
    for label in labels:
        for horizon in horizons:
            matches = [
                row
                for row in coverage
                if row.get("capture_label", row.get("label")) == label
                and float(row["horizon_ms"]) == horizon
            ]
            if len(matches) != 1:
                support_failures.append(f"{label}/{horizon:g}ms coverage row missing or duplicated")
                continue
            row = matches[0]
            reasons = []
            if float(row["paired_coverage"]) < float(decision["minimum_paired_coverage"]):
                reasons.append("paired coverage")
            if int(row["paired_prediction_count"]) < int(
                decision["minimum_paired_targets_per_capture_horizon"]
            ):
                reasons.append("paired target count")
            try:
                nonempty_blocks = int(row["nonempty_block_count"])
            except KeyError:
                try:
                    nonempty_blocks = int(
                        _summary_lookup(
                            summaries,
                            "capture",
                            label,
                            horizon,
                            str(decision["baseline_method"]),
                        )["block_count"]
                    )
                except (KeyError, ValueError):
                    nonempty_blocks = 0
            if nonempty_blocks < int(decision["minimum_nonempty_blocks_per_capture_horizon"]):
                reasons.append("nonempty recording blocks")
            if reasons:
                support_failures.append(f"{label}/{horizon:g}ms below " + ", ".join(reasons))
            coverage_results.append(
                {
                    "capture_label": label,
                    "horizon_ms": horizon,
                    "passes": not reasons,
                    "paired_coverage": row["paired_coverage"],
                    "paired_prediction_count": row["paired_prediction_count"],
                    "nonempty_block_count": nonempty_blocks,
                }
            )

    effect_results: list[dict[str, object]] = []
    if not support_failures:
        for horizon in horizons:
            try:
                aggregate_baseline = float(
                    _summary_lookup(
                        summaries,
                        "equal_capture",
                        "ALL",
                        horizon,
                        str(decision["baseline_method"]),
                    )["odd_block_capture_equal_rms_hz"]
                )
                aggregate_challenger = float(
                    _summary_lookup(
                        summaries,
                        "equal_capture",
                        "ALL",
                        horizon,
                        str(decision["challenger_method"]),
                    )["odd_block_capture_equal_rms_hz"]
                )
                per_capture = {}
                for label in labels:
                    baseline = float(
                        _summary_lookup(
                            summaries,
                            "capture",
                            label,
                            horizon,
                            str(decision["baseline_method"]),
                        )["odd_block_equal_rms_hz"]
                    )
                    challenger = float(
                        _summary_lookup(
                            summaries,
                            "capture",
                            label,
                            horizon,
                            str(decision["challenger_method"]),
                        )["odd_block_equal_rms_hz"]
                    )
                    per_capture[label] = challenger / baseline
            except (KeyError, ValueError, ZeroDivisionError):
                support_failures.append(f"{horizon:g}ms paired effect summaries unavailable")
                continue
            aggregate_ratio = aggregate_challenger / aggregate_baseline
            worst_ratio = max(per_capture.values())
            effect_results.append(
                {
                    "horizon_ms": horizon,
                    "equal_capture_rms_ratio": aggregate_ratio,
                    "worst_capture_rms_ratio": worst_ratio,
                    "per_capture_rms_ratio": per_capture,
                    "passes": aggregate_ratio <= float(decision["maximum_equal_capture_rms_ratio"])
                    and worst_ratio <= float(decision["maximum_per_capture_rms_ratio"]),
                }
            )

    if support_failures:
        status = "inconclusive"
        reason = "one or more frozen provenance/support gates failed"
    elif all(bool(row["passes"]) for row in effect_results) and len(effect_results) == len(
        horizons
    ):
        status = "advance"
        reason = "fixed 500 ms passed every frozen aggregate and per-capture effect gate"
    else:
        status = "scientific_fail"
        reason = "fixed 500 ms failed one or more frozen holdout effect gates"
    return {
        "status": status,
        "reason": reason,
        "support_failures": support_failures,
        "coverage_results": coverage_results,
        "effect_results": effect_results,
        "next_step": decision["advance_on_pass"] if status == "advance" else None,
        "support_complete": not support_failures,
        "all_required_horizons_pass": status == "advance",
    }


def _write_csv(path: Path, rows: tuple[dict[str, object], ...]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _render_comparison(path: Path, evaluation: Evaluation, config: dict[str, Any]) -> None:
    """Render the preregistered Matplotlib-only holdout comparison."""

    figure = Figure(figsize=(15.0, 10.5), dpi=150, constrained_layout=True)
    axes = figure.subplots(2, 2)
    horizons = tuple(float(value) for value in config["forecast_horizons_ms"])
    labels = tuple(str(value) for value in config["expected_labels"])

    axis = axes[0, 0]
    for method in METHODS:
        values = []
        for horizon in horizons:
            try:
                value = float(
                    _summary_lookup(
                        evaluation.summaries,
                        "equal_capture",
                        "ALL",
                        horizon,
                        method,
                    )["odd_block_capture_equal_rms_hz"]
                )
            except ValueError:
                value = math.nan
            values.append(value)
        axis.plot(
            horizons,
            values,
            marker="o",
            color=_COLORS[method],
            label=_LABELS[method],
        )
    axis.set_title("A  Future odd-Qin CFO forecast error")
    axis.set_xlabel("forecast horizon (ms)")
    axis.set_ylabel("equal-capture, block-equal RMS (Hz)")
    axis.grid(alpha=0.25)
    axis.legend(frameon=False)

    axis = axes[0, 1]
    offsets = np.linspace(-0.24, 0.24, len(horizons))
    x = np.arange(len(labels), dtype=float)
    for offset, horizon in zip(offsets, horizons, strict=True):
        effect = next(
            (
                row
                for row in evaluation.comparison_effects
                if row["candidate_method"] == METHOD_FIXED_500
                and float(row["horizon_ms"]) == horizon
            ),
            None,
        )
        ratios = (
            [float(effect["per_capture_ratio"][label]) for label in labels]
            if effect is not None
            else [math.nan] * len(labels)
        )
        axis.scatter(x + offset, ratios, s=35, label=f"{horizon:g} ms")
    axis.axhline(1.0, color="#111827", linewidth=1.0)
    axis.axhline(
        float(config["decision"]["maximum_per_capture_rms_ratio"]),
        color="#dc2626",
        linewidth=1.0,
        linestyle="--",
        label="frozen worst-capture gate",
    )
    axis.set_xticks(x, labels)
    axis.set_ylabel("fixed 500 / fixed 125 RMS")
    axis.set_title("B  Capture-level generalization")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(frameon=False, ncols=2, fontsize=8)

    axis = axes[1, 0]
    width = 0.22
    for index, horizon in enumerate(horizons):
        values = [
            next(
                (
                    float(row["paired_coverage"])
                    for row in evaluation.coverage
                    if row.get("capture_label", row.get("label")) == label
                    and float(row["horizon_ms"]) == horizon
                ),
                0.0,
            )
            for label in labels
        ]
        axis.bar(x + (index - 1) * width, values, width=width, label=f"{horizon:g} ms")
    axis.axhline(
        float(config["decision"]["minimum_paired_coverage"]),
        color="#dc2626",
        linewidth=1.0,
        linestyle="--",
    )
    axis.set_xticks(x, labels)
    axis.set_ylim(0.0, 1.05)
    axis.set_ylabel("paired target coverage")
    axis.set_title("C  Frozen support gate")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(frameon=False, fontsize=8)

    axis = axes[1, 1]
    fixed = [
        row for row in evaluation.traces if row["method"] in {METHOD_FIXED_125, METHOD_FIXED_500}
    ]
    for label_index, label in enumerate(labels):
        selected = [row for row in fixed if row["capture_label"] == label]
        if not selected:
            continue
        baseline = {
            int(row["frame_start_sample"]): float(row["rate_hz_s"])
            for row in selected
            if row["method"] == METHOD_FIXED_125
        }
        differences = [
            float(row["rate_hz_s"]) - baseline[int(row["frame_start_sample"])]
            for row in selected
            if row["method"] == METHOD_FIXED_500 and int(row["frame_start_sample"]) in baseline
        ]
        if differences:
            axis.boxplot(
                differences,
                positions=[label_index],
                widths=0.55,
                showfliers=False,
                patch_artist=True,
                boxprops={"facecolor": "#bfdbfe", "edgecolor": "#2563eb"},
                medianprops={"color": "#111827"},
            )
    axis.axhline(0.0, color="#111827", linewidth=1.0)
    axis.set_xticks(x, labels)
    axis.set_ylabel("500 ms minus 125 ms rate (Hz/s)")
    axis.set_title("D  Rate-estimate change")
    axis.grid(axis="y", alpha=0.25)

    figure.suptitle(
        "Frozen H1–H7 frame-CFO holdout: independent ≤2 s epoch-bound tiles",
        fontsize=15,
    )
    figure.savefig(path, metadata={"Software": "Matplotlib"})


def _write_checkpoint_index(checkpoint_root: Path, replays: tuple[TileReplay, ...]) -> Path:
    entries = []
    for replay in sorted(replays, key=lambda value: value.tile.tile_id):
        path = _checkpoint_path(checkpoint_root, replay.tile)
        entries.append(
            {
                "tile_id": replay.tile.tile_id,
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    index_path = checkpoint_root / "checkpoint-index.json"
    _atomic_write(
        index_path,
        _json_bytes(
            {
                "schema": "org.leo.research.recent-adaptive-cfo-checkpoint-index/v1",
                "tiles": entries,
            }
        ),
    )
    return index_path


def _write_replay_archive(
    path: Path,
    replays: tuple[TileReplay, ...],
    config: dict[str, Any],
) -> None:
    """Persist the frame-level replay inputs as one deterministic artifact."""

    document = {
        "schema": "org.leo.research.recent-adaptive-cfo-tile-replays/v1",
        "holdout_input_sha256": config["holdout_input_sha256"],
        "replay_config_sha256": config["_replay_config_sha256"],
        "tile_replays": [asdict(replay) for replay in replays],
    }
    buffer = io.BytesIO()
    with gzip.GzipFile(
        filename="",
        mode="wb",
        fileobj=buffer,
        compresslevel=9,
        mtime=0,
    ) as destination:
        destination.write(_json_bytes(document))
    _atomic_write(path, buffer.getvalue())


def run(
    *,
    inputs_path: Path,
    holdout_path: Path,
    bulk_root: Path,
    checkpoint_root: Path,
    output_root: Path,
    maximum_tiles: int | None,
) -> dict[str, object]:
    _validate_write_roots(checkpoint_root, output_root)
    if maximum_tiles is not None and output_root.resolve() == DEFAULT_OUTPUT_ROOT.resolve():
        raise ValueError("a bounded smoke replay cannot target the canonical output root")
    config = _validate_config(_load_object(inputs_path))
    config = dict(config)
    config["_replay_config_sha256"] = _sha256(inputs_path)
    dwells = _load_holdout(holdout_path, config)
    all_tiles = tuple(
        tile
        for item in dwells
        for tile in _plan_tiles(item, float(config["maximum_tile_duration_s"]))
    )
    if maximum_tiles is not None:
        if maximum_tiles < 1:
            raise ValueError("maximum tiles must be positive")
        selected_tiles = all_tiles[:maximum_tiles]
    else:
        selected_tiles = all_tiles
    item_by_label = {str(item["label"]): item for item in dwells}
    store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
    tile_failures: list[dict[str, object]] = []
    try:
        replay_rows: list[TileReplay] = []
        for index, tile in enumerate(selected_tiles, start=1):
            print(
                f"[{index}/{len(selected_tiles)}] replaying {tile.tile_id} "
                f"[{tile.start_s:.6f}, {tile.stop_s:.6f}) s",
                flush=True,
            )
            try:
                replay = _load_or_analyze_tile(
                    checkpoint_root,
                    store,
                    bulk_root,
                    item_by_label[tile.capture_label],
                    tile,
                    config,
                )
            except (OSError, ValueError) as error:
                failure = {
                    "tile": asdict(tile),
                    "error_type": type(error).__name__,
                    "reason": str(error),
                }
                tile_failures.append(failure)
                print(
                    f"[{index}/{len(selected_tiles)}] {tile.tile_id}: unsupported "
                    f"({type(error).__name__}: {error})",
                    flush=True,
                )
                continue
            replay_rows.append(replay)
            print(
                f"[{index}/{len(selected_tiles)}] {tile.tile_id}: "
                f"{sum(bool(row['training_supported']) for row in replay.frame_inventory)}/"
                f"{replay.opportunity_count} even-Qin supported",
                flush=True,
            )
        replays = tuple(replay_rows)
    finally:
        store.close()
    output_root.mkdir(parents=True, exist_ok=True)
    external_checkpoint_index = _write_checkpoint_index(checkpoint_root, replays)
    checkpoint_index = output_root / "checkpoint-index.json"
    _atomic_write(checkpoint_index, external_checkpoint_index.read_bytes())
    replay_archive = output_root / "tile-replays.json.gz"
    _write_replay_archive(replay_archive, replays, config)
    full_run = maximum_tiles is None and not tile_failures and len(replays) == len(all_tiles)
    summary_path = output_root / "summary.json"
    manifest_path = output_root / "artifact-manifest.json"
    if not full_run:
        bounded_smoke = maximum_tiles is not None
        reason = (
            "bounded smoke replay"
            if bounded_smoke
            else "one or more frozen tiles failed provenance, continuity, or fresh binding"
        )
        result: dict[str, object] = {
            "schema": "org.leo.research.recent-adaptive-cfo-holdout-summary/v1",
            "full_frozen_run": False,
            "full_frozen_attempt": not bounded_smoke,
            "decision": {"status": "inconclusive", "reason": reason},
            "planned_tile_count": len(all_tiles),
            "attempted_tile_count": len(selected_tiles),
            "completed_tile_count": len(replays),
            "tile_failures": tile_failures,
            "input_sha256": {
                "holdout": _sha256(holdout_path),
                "replay_config": _sha256(inputs_path),
            },
        }
        _atomic_write(summary_path, _json_bytes(result))
        artifacts = {
            "summary": {
                "path": summary_path.name,
                "bytes": summary_path.stat().st_size,
                "sha256": _sha256(summary_path),
            },
            "checkpoint_index": {
                "path": checkpoint_index.name,
                "bytes": checkpoint_index.stat().st_size,
                "sha256": _sha256(checkpoint_index),
            },
            "tile_replays": {
                "path": replay_archive.name,
                "bytes": replay_archive.stat().st_size,
                "sha256": _sha256(replay_archive),
            },
        }
        _atomic_write(
            manifest_path,
            _json_bytes(
                {
                    "schema": "org.leo.research.recent-adaptive-cfo-holdout-artifacts/v1",
                    "full_frozen_run": False,
                    "artifacts": artifacts,
                }
            ),
        )
        return result

    evaluation = _evaluate_tiles(replays, config)
    decision = _decision_status(evaluation.summaries, evaluation.coverage, config)
    forecast_path = output_root / "forecast-rows.csv"
    trace_path = output_root / "rate-tracks.json"
    comparison_path = output_root / "comparison.png"
    _write_csv(forecast_path, evaluation.forecasts)
    _atomic_write(
        trace_path,
        _json_bytes(
            {
                "schema": "org.leo.research.recent-adaptive-cfo-holdout-rate-tracks/v1",
                "rows": list(evaluation.traces),
            }
        ),
    )
    _render_comparison(comparison_path, evaluation, config)
    result = {
        "schema": "org.leo.research.recent-adaptive-cfo-holdout-summary/v1",
        "full_frozen_run": True,
        "candidate_only": True,
        "measurement_name": "receiver-relative apparent CFO and CFO rate",
        "carrier_phase_connected": False,
        "receiver_relative_timing_used_for_doppler": False,
        "epoch_and_alias_authority": "fresh exact upstream GLRT branch source per tile",
        "training_symbols": "past even Qin only",
        "response_symbols": "future odd Qin; withheld from all tracker decisions",
        "tile_policy": config["policies"],
        "planned_tile_count": len(all_tiles),
        "completed_tile_count": len(replays),
        "capture_count": len(dwells),
        "input_sha256": {
            "holdout": _sha256(holdout_path),
            "replay_config": _sha256(inputs_path),
        },
        "implementation_sha256": {
            "tool": _sha256(Path(__file__)),
            "raw_frame_cfo_tool": _sha256(Path(frame_cfo_tool.__file__)),
            "frame_profile": _sha256(Path(__file__).parents[1] / "src/leo/analysis/qam/pilot.py"),
            "adaptive_tracker": _sha256(
                Path(__file__).parents[1] / "src/leo/analysis/research/adaptive_frame_cfo.py"
            ),
        },
        "configuration": {
            key: value
            for key, value in config.items()
            if key not in {"_replay_config_sha256", "policies"}
        },
        "methods": list(METHODS),
        "tile_replays": [
            {
                "tile": asdict(replay.tile),
                "frame_epoch_sample": replay.frame_epoch_sample,
                "source_id": replay.source_id,
                "source_detection_time_s": replay.source_detection_time_s,
                "source_bound_cfo_hz": replay.source_bound_cfo_hz,
                "opportunity_count": replay.opportunity_count,
                "training_supported_count": sum(
                    bool(row["training_supported"]) for row in replay.frame_inventory
                ),
            }
            for replay in replays
        ],
        "forecast_row_count": len(evaluation.forecasts),
        "paired_target_count": len(evaluation.forecasts) // len(METHODS),
        "history_selection_counts": {
            label: dict(
                sorted(
                    Counter(
                        f"{float(row['selected_history_ms']):g}ms"
                        for row in evaluation.traces
                        if row["capture_label"] == label and row["method"] == METHOD_ADAPTIVE
                    ).items()
                )
            )
            for label in config["expected_labels"]
        },
        "paired_coverage": list(evaluation.coverage),
        "forecast_summaries": list(evaluation.summaries),
        "paired_comparison_effects": list(evaluation.comparison_effects),
        "decision": decision,
    }
    _atomic_write(summary_path, _json_bytes(result))
    artifacts = {
        name: {"path": path.name, "bytes": path.stat().st_size, "sha256": _sha256(path)}
        for name, path in (
            ("summary", summary_path),
            ("forecast_rows", forecast_path),
            ("rate_tracks", trace_path),
            ("comparison_plot", comparison_path),
            ("tile_replays", replay_archive),
        )
    }
    artifacts["checkpoint_index"] = {
        "path": checkpoint_index.name,
        "bytes": checkpoint_index.stat().st_size,
        "sha256": _sha256(checkpoint_index),
    }
    _atomic_write(
        manifest_path,
        _json_bytes(
            {
                "schema": "org.leo.research.recent-adaptive-cfo-holdout-artifacts/v1",
                "full_frozen_run": True,
                "artifacts": artifacts,
            }
        ),
    )
    return result


def main() -> int:
    arguments = _arguments()
    result = run(
        inputs_path=arguments.inputs,
        holdout_path=arguments.holdout,
        bulk_root=arguments.bulk_root,
        checkpoint_root=arguments.checkpoint_root,
        output_root=arguments.output_root,
        maximum_tiles=arguments.maximum_tiles,
    )
    print(json.dumps(stable_measurement_floats(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
