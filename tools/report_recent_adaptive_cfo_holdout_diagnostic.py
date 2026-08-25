#!/usr/bin/env python3
"""Report diagnostic-only results from an incomplete frozen CFO holdout replay.

This tool never opens recording IQ.  It verifies the persisted incomplete replay,
its external canonical checkpoints, and every input digest before evaluating the
successful tiles.  The frozen holdout decision remains inconclusive; partial
performance values are explicitly descriptive and cannot satisfy the advancement
gate.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from matplotlib import colors
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

matplotlib.use("Agg")

from leo.analysis.starlink.local_doppler import stable_measurement_floats

try:
    import prototype_recent_adaptive_cfo_holdout as holdout
except ModuleNotFoundError:  # pragma: no cover - imported from repository root
    from tools import prototype_recent_adaptive_cfo_holdout as holdout


DEFAULT_INPUT_ROOT = Path("reports/figures/2026_08_25_recent_adaptive_cfo_holdout")
DEFAULT_CHECKPOINT_ROOT = Path("reports/checkpoints/2026_08_25_recent_adaptive_cfo_holdout")
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_25_recent_adaptive_cfo_holdout_diagnostic")
DEFAULT_REPLAY_CONFIG = Path("config/analysis/recent-adaptive-cfo-holdout-replay-v1.json")
DEFAULT_HOLDOUT = Path("config/analysis/recent-adaptive-cfo-holdout-v1.json")
TRACK_HORIZON_MS = 125.0

_ARTIFACT_NAMES = {"summary", "checkpoint_index", "tile_replays"}
_ARCHIVE_FIELDS = {
    "frame_epoch_sample",
    "frame_inventory",
    "opportunity_count",
    "source_bound_cfo_hz",
    "source_detection_time_s",
    "source_id",
    "tile",
}


@dataclass(frozen=True, slots=True)
class VerifiedInputs:
    config: dict[str, Any]
    summary: dict[str, Any]
    dwells: tuple[dict[str, Any], ...]
    planned_tiles: tuple[holdout.TileSpec, ...]
    replays: tuple[holdout.TileReplay, ...]
    implementation_sha256: dict[str, str]
    input_sha256: dict[str, str]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--checkpoint-root", type=Path, default=DEFAULT_CHECKPOINT_ROOT)
    parser.add_argument("--replay-config", type=Path, default=DEFAULT_REPLAY_CONFIG)
    parser.add_argument("--holdout", type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


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


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _load_object(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _validate_output_root(input_root: Path, checkpoint_root: Path, output_root: Path) -> None:
    source = input_root.resolve()
    checkpoints = checkpoint_root.resolve()
    output = output_root.resolve()
    qnap = holdout.QNAP_READ_ONLY_ROOT.resolve()
    if output in {source, checkpoints}:
        raise ValueError("diagnostic output must be distinct from input and checkpoint roots")
    if output == qnap or qnap in output.parents:
        raise ValueError("diagnostic output cannot be beneath read-only /mnt/qnap01")


def _verify_artifact_manifest(input_root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    manifest_path = input_root / "artifact-manifest.json"
    manifest = _load_object(manifest_path)
    if (
        set(manifest) != {"schema", "full_frozen_run", "artifacts"}
        or manifest.get("schema") != "org.leo.research.recent-adaptive-cfo-holdout-artifacts/v1"
        or manifest.get("full_frozen_run") is not False
        or not isinstance(manifest.get("artifacts"), dict)
        or set(manifest["artifacts"]) != _ARTIFACT_NAMES
    ):
        raise ValueError("incomplete holdout artifact manifest is not closed")
    digests = {"artifact_manifest": _sha256(manifest_path)}
    for name, row in manifest["artifacts"].items():
        if not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}:
            raise ValueError("holdout artifact entry is not closed")
        relative = Path(str(row["path"]))
        if relative.name != str(relative) or relative.is_absolute():
            raise ValueError("holdout artifact path must be a sibling filename")
        path = input_root / relative
        if (
            not path.is_file()
            or path.stat().st_size != int(row["bytes"])
            or _sha256(path) != row["sha256"]
        ):
            raise ValueError(f"holdout artifact digest mismatch: {name}")
        digests[name] = str(row["sha256"])
    return manifest, digests


def _rehydrate_archive(path: Path) -> tuple[dict[str, Any], tuple[holdout.TileReplay, ...]]:
    with gzip.open(path, "rt", encoding="utf-8") as source:
        archive = json.load(source)
    if (
        not isinstance(archive, dict)
        or set(archive)
        != {"schema", "holdout_input_sha256", "replay_config_sha256", "tile_replays"}
        or archive.get("schema") != "org.leo.research.recent-adaptive-cfo-tile-replays/v1"
        or not isinstance(archive.get("tile_replays"), list)
    ):
        raise ValueError("tile replay archive is not closed")
    output: list[holdout.TileReplay] = []
    for raw in archive["tile_replays"]:
        if not isinstance(raw, dict) or set(raw) != _ARCHIVE_FIELDS:
            raise ValueError("archived tile replay is not closed")
        tile_raw = raw["tile"]
        if not isinstance(tile_raw, dict) or set(tile_raw) != {
            "capture_label",
            "tile_id",
            "tile_index",
            "start_s",
            "stop_s",
        }:
            raise ValueError("archived tile identity is not closed")
        tile = holdout.TileSpec(**tile_raw)
        inventory = holdout._validate_inventory(raw["frame_inventory"], tile)
        output.append(
            holdout.TileReplay(
                tile=tile,
                frame_inventory=inventory,
                frame_epoch_sample=int(raw["frame_epoch_sample"]),
                source_id=str(raw["source_id"]),
                source_detection_time_s=float(raw["source_detection_time_s"]),
                source_bound_cfo_hz=float(raw["source_bound_cfo_hz"]),
                opportunity_count=int(raw["opportunity_count"]),
            )
        )
    ordered = tuple(
        sorted(output, key=lambda value: (value.tile.capture_label, value.tile.tile_index))
    )
    if len({value.tile.tile_id for value in ordered}) != len(ordered):
        raise ValueError("archived tile identities are not unique")
    return archive, ordered


def _verify_checkpoints(
    checkpoint_root: Path,
    checkpoint_index_path: Path,
    items: dict[str, dict[str, Any]],
    archive_replays: tuple[holdout.TileReplay, ...],
    config: dict[str, Any],
) -> dict[str, str]:
    index = _load_object(checkpoint_index_path)
    if (
        set(index) != {"schema", "tiles"}
        or index.get("schema") != "org.leo.research.recent-adaptive-cfo-checkpoint-index/v1"
        or not isinstance(index.get("tiles"), list)
    ):
        raise ValueError("checkpoint index is not closed")
    by_id = {value.tile.tile_id: value for value in archive_replays}
    if len(index["tiles"]) != len(by_id):
        raise ValueError("checkpoint index and replay archive counts differ")
    implementations: set[str] = set()
    implementation_maps: list[dict[str, str]] = []
    indexed_ids: set[str] = set()
    for row in index["tiles"]:
        if not isinstance(row, dict) or set(row) != {"tile_id", "path", "bytes", "sha256"}:
            raise ValueError("checkpoint index entry is not closed")
        tile_id = str(row["tile_id"])
        if tile_id in indexed_ids:
            raise ValueError("checkpoint index tile identities are duplicated")
        indexed_ids.add(tile_id)
        replay = by_id.get(tile_id)
        if replay is None or row["path"] != f"{tile_id}.json":
            raise ValueError("checkpoint index tile identity mismatch")
        path = checkpoint_root / str(row["path"])
        raw = path.read_bytes()
        if len(raw) != int(row["bytes"]) or _sha256(path) != row["sha256"]:
            raise ValueError(f"checkpoint digest mismatch: {tile_id}")
        document = json.loads(raw)
        if not isinstance(document, dict) or raw != holdout._json_bytes(document):
            raise ValueError(f"checkpoint is not canonical: {tile_id}")
        verified = holdout._replay_from_checkpoint(
            document,
            items[replay.tile.capture_label],
            replay.tile,
            config,
        )
        if asdict(verified) != asdict(replay):
            raise ValueError(f"checkpoint and replay archive disagree: {tile_id}")
        contract = document["payload"]["contract"]
        implementation = contract["implementation_sha256"]
        if not isinstance(implementation, dict) or any(
            not isinstance(name, str) or not isinstance(value, str)
            for name, value in implementation.items()
        ):
            raise ValueError("checkpoint implementation provenance is invalid")
        implementation_maps.append(dict(implementation))
        implementations.add(json.dumps(implementation, sort_keys=True))
    if indexed_ids != set(by_id):
        raise ValueError("checkpoint index and replay archive identities differ")
    if len(implementations) != 1 or not implementation_maps:
        raise ValueError("checkpoints do not share one implementation identity")
    return implementation_maps[0]


def _load_verified_inputs(
    input_root: Path,
    checkpoint_root: Path,
    replay_config_path: Path,
    holdout_path: Path,
) -> VerifiedInputs:
    _, artifact_digests = _verify_artifact_manifest(input_root)
    config = holdout._validate_config(holdout._load_object(replay_config_path))
    config = dict(config)
    config["_replay_config_sha256"] = _sha256(replay_config_path)
    dwells = holdout._load_holdout(holdout_path, config)
    summary = _load_object(input_root / "summary.json")
    expected_summary_fields = {
        "schema",
        "full_frozen_run",
        "full_frozen_attempt",
        "decision",
        "planned_tile_count",
        "attempted_tile_count",
        "completed_tile_count",
        "tile_failures",
        "input_sha256",
    }
    if (
        set(summary) != expected_summary_fields
        or summary.get("schema") != "org.leo.research.recent-adaptive-cfo-holdout-summary/v1"
        or summary.get("full_frozen_run") is not False
        or summary.get("full_frozen_attempt") is not True
        or summary.get("decision", {}).get("status") != "inconclusive"
        or summary.get("input_sha256")
        != {"holdout": _sha256(holdout_path), "replay_config": _sha256(replay_config_path)}
    ):
        raise ValueError("incomplete frozen holdout summary is not the expected closed result")
    archive, replays = _rehydrate_archive(input_root / "tile-replays.json.gz")
    if archive["holdout_input_sha256"] != _sha256(holdout_path) or archive[
        "replay_config_sha256"
    ] != _sha256(replay_config_path):
        raise ValueError("tile replay archive input digest mismatch")
    planned_tiles = tuple(
        tile
        for item in dwells
        for tile in holdout._plan_tiles(item, float(config["maximum_tile_duration_s"]))
    )
    replay_ids = {value.tile.tile_id for value in replays}
    failures = summary["tile_failures"]
    if not isinstance(failures, list):
        raise ValueError("tile failures must be a list")
    planned_ids = {value.tile_id for value in planned_tiles}
    planned_by_id = {value.tile_id: value for value in planned_tiles}
    failure_ids: set[str] = set()
    for failure in failures:
        if (
            not isinstance(failure, dict)
            or set(failure) != {"tile", "error_type", "reason"}
            or failure.get("error_type") != "ValueError"
            or failure.get("reason")
            != "selected interval has no exact branch-bound GLRT epoch source"
            or not isinstance(failure.get("tile"), dict)
        ):
            raise ValueError("tile failure record is not the frozen closed failure")
        try:
            failed_tile = holdout.TileSpec(**failure["tile"])
        except TypeError as error:
            raise ValueError("failed tile geometry is not closed") from error
        expected_tile = planned_by_id.get(failed_tile.tile_id)
        if (
            expected_tile is None
            or stable_measurement_floats(asdict(expected_tile)) != failure["tile"]
            or failed_tile.tile_id in failure_ids
        ):
            raise ValueError("failed tile geometry or identity mismatch")
        failure_ids.add(failed_tile.tile_id)
    if (
        replay_ids & failure_ids
        or replay_ids | failure_ids != planned_ids
        or len(replays) != int(summary["completed_tile_count"])
        or len(planned_tiles) != int(summary["planned_tile_count"])
        or int(summary["attempted_tile_count"]) != len(planned_tiles)
    ):
        raise ValueError("planned, completed, and failed tile identities do not close")
    items = {str(item["label"]): item for item in dwells}
    implementation = _verify_checkpoints(
        checkpoint_root,
        input_root / "checkpoint-index.json",
        items,
        replays,
        config,
    )
    return VerifiedInputs(
        config=config,
        summary=summary,
        dwells=dwells,
        planned_tiles=planned_tiles,
        replays=replays,
        implementation_sha256=implementation,
        input_sha256={
            **artifact_digests,
            "holdout": _sha256(holdout_path),
            "replay_config": _sha256(replay_config_path),
        },
    )


def _summary_row(
    rows: tuple[dict[str, object], ...],
    label: str,
    horizon_ms: float,
    method: str,
) -> dict[str, object] | None:
    matches = [
        row
        for row in rows
        if row.get("scope") == "capture"
        and row.get("label") == label
        and float(row["horizon_ms"]) == horizon_ms
        and row.get("method") == method
    ]
    if len(matches) > 1:
        raise ValueError("diagnostic capture summary is duplicated")
    return matches[0] if matches else None


def _diagnostic_payload(
    verified: VerifiedInputs,
    evaluation: holdout.Evaluation,
    decision: dict[str, object],
) -> dict[str, object]:
    replay_by_id = {value.tile.tile_id: value for value in verified.replays}
    failure_by_id = {
        str(value["tile"]["tile_id"]): value for value in verified.summary["tile_failures"]
    }
    tile_support = []
    for tile in verified.planned_tiles:
        replay = replay_by_id.get(tile.tile_id)
        if replay is None:
            failure = failure_by_id[tile.tile_id]
            tile_support.append(
                {
                    **asdict(tile),
                    "status": "fresh_source_unavailable",
                    "opportunity_count": None,
                    "training_supported_count": None,
                    "training_support_fraction": None,
                    "reason": failure["reason"],
                }
            )
            continue
        supported = sum(bool(row["training_supported"]) for row in replay.frame_inventory)
        tile_support.append(
            {
                **asdict(tile),
                "status": "complete",
                "opportunity_count": replay.opportunity_count,
                "training_supported_count": supported,
                "training_support_fraction": supported / replay.opportunity_count,
                "reason": None,
            }
        )
    labels = tuple(str(value) for value in verified.config["expected_labels"])
    horizons = tuple(float(value) for value in verified.config["forecast_horizons_ms"])
    completed_by_label = {
        label: sum(value.tile.capture_label == label for value in verified.replays)
        for label in labels
    }
    planned_by_label = {
        label: sum(value.capture_label == label for value in verified.planned_tiles)
        for label in labels
    }
    capture_complete = {
        label: completed_by_label[label] == planned_by_label[label] for label in labels
    }
    for row in evaluation.forecasts:
        expected_residual = float(row["target_odd_cfo_hz"]) - float(row["prediction_hz"])
        if not math.isclose(
            float(row["odd_residual_hz"]), expected_residual, rel_tol=0.0, abs_tol=1e-9
        ):
            raise ValueError("diagnostic odd-Qin residual identity is invalid")
    coverage_pass = {
        (str(row["capture_label"]), float(row["horizon_ms"])): bool(row["passes"])
        for row in decision["coverage_results"]
    }
    coverage_by_key = {
        (str(row.get("capture_label", row.get("label"))), float(row["horizon_ms"])): row
        for row in evaluation.coverage
    }
    performance: list[dict[str, object]] = []
    for label in labels:
        for horizon in horizons:
            baseline = _summary_row(evaluation.summaries, label, horizon, holdout.METHOD_FIXED_125)
            challenger = _summary_row(
                evaluation.summaries, label, horizon, holdout.METHOD_FIXED_500
            )
            adaptive = _summary_row(evaluation.summaries, label, horizon, holdout.METHOD_ADAPTIVE)
            coverage = coverage_by_key[(label, horizon)]
            if baseline is None or challenger is None or adaptive is None:
                performance.append(
                    {
                        "capture_label": label,
                        "horizon_ms": horizon,
                        "available": False,
                        "numeric_support_status": (
                            "met_on_available_tiles"
                            if coverage_pass[(label, horizon)]
                            else "sparse"
                        ),
                        "capture_provenance_complete": capture_complete[label],
                        "cell_evaluable": False,
                        "paired_prediction_count": coverage["paired_prediction_count"],
                        "nonempty_block_count": coverage["nonempty_block_count"],
                        "paired_coverage": coverage["paired_coverage"],
                        "fixed_125_rms_hz": None,
                        "fixed_500_rms_hz": None,
                        "fixed_500_over_125_ratio": None,
                        "adaptive_rms_hz": None,
                        "adaptive_over_125_ratio": None,
                    }
                )
                continue
            rms_125 = float(baseline["odd_block_equal_rms_hz"])
            rms_500 = float(challenger["odd_block_equal_rms_hz"])
            rms_adaptive = float(adaptive["odd_block_equal_rms_hz"])
            performance.append(
                {
                    "capture_label": label,
                    "horizon_ms": horizon,
                    "available": True,
                    "numeric_support_status": (
                        "met_on_available_tiles" if coverage_pass[(label, horizon)] else "sparse"
                    ),
                    "capture_provenance_complete": capture_complete[label],
                    "cell_evaluable": capture_complete[label] and coverage_pass[(label, horizon)],
                    "paired_prediction_count": coverage["paired_prediction_count"],
                    "nonempty_block_count": coverage["nonempty_block_count"],
                    "paired_coverage": coverage["paired_coverage"],
                    "fixed_125_rms_hz": rms_125,
                    "fixed_500_rms_hz": rms_500,
                    "fixed_500_over_125_ratio": rms_500 / rms_125,
                    "adaptive_rms_hz": rms_adaptive,
                    "adaptive_over_125_ratio": rms_adaptive / rms_125,
                }
            )
    capture_intervals = [
        {
            "capture_label": str(item["label"]),
            "start_s": float(item["analysis_start_s"]),
            "stop_s": float(item["analysis_stop_s"]),
        }
        for item in verified.dwells
    ]
    exact_stride_labels = [label for label in labels if capture_complete[label]]
    reindexed_labels = [label for label in labels if not capture_complete[label]]
    fully_replayed_support_failures = [
        {
            "capture_label": label,
            "coverage": [
                row
                for row in evaluation.coverage
                if row.get("capture_label", row.get("label")) == label
            ],
        }
        for label in exact_stride_labels
        if not all(coverage_pass[(label, horizon)] for horizon in horizons)
    ]
    adaptive_history_counts: dict[str, int] = {}
    for row in evaluation.forecasts:
        if row["method"] != holdout.METHOD_ADAPTIVE:
            continue
        key = f"{float(row['selected_history_ms']):g}"
        adaptive_history_counts[key] = adaptive_history_counts.get(key, 0) + 1
    paired_target_count = len(evaluation.forecasts) // len(holdout.METHODS)
    capture_replay_counts = [
        {
            "capture_label": label,
            "planned_tile_count": planned_by_label[label],
            "completed_tile_count": completed_by_label[label],
            "capture_provenance_complete": capture_complete[label],
        }
        for label in labels
    ]
    return {
        "schema": "org.leo.research.recent-adaptive-cfo-holdout-diagnostic/v1",
        "diagnostic_only": True,
        "promotion_claimed": False,
        "full_frozen_run": False,
        "decision": verified.summary["decision"],
        "counterfactual_decision": decision,
        "confirmatory_gate_evaluated": False,
        "confirmatory_effect_gate_evaluated": False,
        "claim_warning": (
            "incomplete successful-tile diagnostic cannot advance, fail, tune, or promote"
        ),
        "reason": (
            "five tiles failed fresh source binding, and fully replayed H4/H5 independently "
            "failed the frozen support minimums"
        ),
        "planned_tile_count": len(verified.planned_tiles),
        "completed_tile_count": len(verified.replays),
        "failed_tile_count": len(verified.planned_tiles) - len(verified.replays),
        "capture_replay_counts": capture_replay_counts,
        "capture_intervals": capture_intervals,
        "tile_support": tile_support,
        "coverage": list(evaluation.coverage),
        "performance": performance,
        "aggregate_effect": None,
        "aggregate_effect_reason": (
            "the seven-capture paired support matrix is incomplete; no aggregate effect is defined"
        ),
        "fully_replayed_capture_support_failures": fully_replayed_support_failures,
        "forecast_row_count": len(evaluation.forecasts),
        "paired_target_count": paired_target_count,
        "adaptive_history_selection_counts": adaptive_history_counts,
        "residual_definition": "odd_residual_hz = target_odd_cfo_hz - prediction_hz",
        "implementation_sha256": {
            **verified.implementation_sha256,
            "diagnostic_reporter": _sha256(Path(__file__)),
        },
        "input_sha256": verified.input_sha256,
        "disclosures": {
            "measurement": "receiver-relative apparent CFO and CFO rate",
            "future_odd_qin": "fit-withheld within each successfully bound tile",
            "target_mask": "conditioned on target even-Qin support",
            "upstream_source_epoch_alias": "GLRT-selected and not end-to-end odd-independent",
            "carrier_phase_connected": False,
            "receiver_relative_timing_used": False,
            "application_refills": "verified counter-contiguous refills are not resets",
            "posthoc_target_mask": (
                "successful tiles are capture-reindexed after five missing tiles; the 15-frame "
                "stride therefore is not the unavailable frozen full-run target mask"
            ),
            "exact_frozen_stride_captures": exact_stride_labels,
            "posthoc_reindexed_captures": reindexed_labels,
            "claim_limit": (
                "incomplete successful-tile diagnostic cannot advance, fail, tune, or promote"
            ),
        },
    }


def _render_comparison(path: Path, payload: dict[str, object]) -> None:
    labels = [str(value["capture_label"]) for value in payload["capture_intervals"]]
    horizons = sorted({float(value["horizon_ms"]) for value in payload["coverage"]})
    interval_by_label = {
        str(value["capture_label"]): value for value in payload["capture_intervals"]
    }
    figure = Figure(figsize=(15.5, 10.5), dpi=150, constrained_layout=True)
    axes = figure.subplots(2, 2)

    axis = axes[0, 0]
    cmap = matplotlib.colormaps["viridis"]
    norm = colors.Normalize(vmin=0.0, vmax=1.0)
    for y, label in enumerate(labels):
        interval = interval_by_label[label]
        start = float(interval["start_s"])
        span = float(interval["stop_s"]) - start
        for row in payload["tile_support"]:
            if row["capture_label"] != label:
                continue
            left = (float(row["start_s"]) - start) / span
            width = (float(row["stop_s"]) - float(row["start_s"])) / span
            fraction = row["training_support_fraction"]
            if fraction is None:
                patch = Rectangle(
                    (left, y - 0.36),
                    width,
                    0.72,
                    facecolor="white",
                    edgecolor="#dc2626",
                    hatch="////",
                    linewidth=1.2,
                )
                axis.add_patch(patch)
                axis.plot([left, left + width], [y - 0.34, y + 0.34], color="#dc2626", lw=1)
                axis.plot([left, left + width], [y + 0.34, y - 0.34], color="#dc2626", lw=1)
            else:
                axis.add_patch(
                    Rectangle(
                        (left, y - 0.36),
                        width,
                        0.72,
                        facecolor=cmap(norm(float(fraction))),
                        edgecolor="white",
                        linewidth=0.6,
                    )
                )
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(len(labels) - 0.45, -0.55)
    axis.set_yticks(np.arange(len(labels)), labels)
    axis.set_xlabel("fraction of frozen capture interval")
    axis.set_title("A  Even-Qin training support by frozen tile")
    axis.grid(axis="x", alpha=0.2)
    colorbar = figure.colorbar(
        matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap), ax=axis, fraction=0.045, pad=0.02
    )
    colorbar.set_label("supported / opportunities")

    axis = axes[0, 1]
    coverage_by_key = {
        (str(row["capture_label"]), float(row["horizon_ms"])): row for row in payload["coverage"]
    }
    coverage = np.zeros((len(labels), len(horizons)), dtype=float)
    for i, label in enumerate(labels):
        for j, horizon in enumerate(horizons):
            row = coverage_by_key[(label, horizon)]
            coverage[i, j] = float(row["paired_coverage"])
    image = axis.imshow(coverage, vmin=0.0, vmax=1.0, cmap="Blues", aspect="auto")
    axis.set_xticks(np.arange(len(horizons)), [f"{value:g} ms" for value in horizons])
    axis.set_yticks(np.arange(len(labels)), labels)
    axis.set_title("B  Paired forecast coverage (conditional on eligible targets)")
    performance_by_key = {
        (str(row["capture_label"]), float(row["horizon_ms"])): row for row in payload["performance"]
    }
    for i, label in enumerate(labels):
        for j, horizon in enumerate(horizons):
            row = performance_by_key[(label, horizon)]
            count = int(row["paired_prediction_count"])
            eligible = coverage_by_key[(label, horizon)]["eligible_target_count"]
            axis.text(
                j,
                i,
                f"{coverage[i, j] * 100:.0f}%\n{count}/{eligible}",
                ha="center",
                va="center",
                fontsize=8,
                color="white" if coverage[i, j] > 0.55 else "#111827",
            )
            if bool(row["cell_evaluable"]):
                axis.add_patch(
                    Rectangle((j - 0.48, i - 0.48), 0.96, 0.96, fill=False, ec="#16a34a", lw=2)
                )
            elif row["numeric_support_status"] == "met_on_available_tiles":
                axis.add_patch(
                    Rectangle((j - 0.48, i - 0.48), 0.96, 0.96, fill=False, ec="#d97706", lw=2)
                )
    figure.colorbar(image, ax=axis, fraction=0.045, pad=0.02)

    axis = axes[1, 0]
    ratios = np.full((len(labels), len(horizons)), np.nan)
    for i, label in enumerate(labels):
        for j, horizon in enumerate(horizons):
            row = performance_by_key[(label, horizon)]
            if row["available"]:
                ratios[i, j] = float(row["fixed_500_over_125_ratio"])
    ratio_norm = colors.TwoSlopeNorm(vmin=0.3, vcenter=1.0, vmax=1.3)
    ratio_image = axis.imshow(ratios, norm=ratio_norm, cmap="RdBu_r", aspect="auto")
    axis.set_xticks(np.arange(len(horizons)), [f"{value:g} ms" for value in horizons])
    axis.set_yticks(np.arange(len(labels)), labels)
    axis.set_title("C  RMS ratios vs fixed 125 (color = fixed 500)")
    for i, label in enumerate(labels):
        for j, horizon in enumerate(horizons):
            row = performance_by_key[(label, horizon)]
            text = (
                "—"
                if not row["available"]
                else (
                    f"500 {float(row['fixed_500_over_125_ratio']):.3f}\n"
                    f"A {float(row['adaptive_over_125_ratio']):.3f}"
                )
            )
            axis.text(j, i, text, ha="center", va="center", fontsize=9)
            if bool(row["cell_evaluable"]):
                axis.add_patch(
                    Rectangle((j - 0.48, i - 0.48), 0.96, 0.96, fill=False, ec="#16a34a", lw=2)
                )
            elif row["numeric_support_status"] == "met_on_available_tiles":
                axis.add_patch(
                    Rectangle((j - 0.48, i - 0.48), 0.96, 0.96, fill=False, ec="#d97706", lw=2)
                )
    figure.colorbar(ratio_image, ax=axis, fraction=0.045, pad=0.02)

    axis = axes[1, 1]
    for row in payload["performance"]:
        if not row["available"]:
            continue
        baseline = float(row["fixed_125_rms_hz"])
        evaluable = bool(row["cell_evaluable"])
        partial_support = row["numeric_support_status"] == "met_on_available_tiles"
        for value_name, color, marker, suffix in (
            ("fixed_500_rms_hz", "#2563eb", "o", "500"),
            ("adaptive_rms_hz", "#d97706", "^", "A"),
        ):
            value = float(row[value_name])
            axis.scatter(
                baseline,
                value,
                s=55 if evaluable else 35,
                marker=marker,
                facecolor=color if evaluable else "none",
                edgecolor=color,
                linewidth=1.2,
                alpha=1.0 if partial_support else 0.5,
            )
            if suffix == "500":
                axis.annotate(
                    f"{row['capture_label']}/{float(row['horizon_ms']):g}",
                    (baseline, value),
                    xytext=(4, 3),
                    textcoords="offset points",
                    fontsize=7,
                )
    limits = [20.0, 700.0]
    axis.plot(limits, limits, color="#111827", linestyle="--", linewidth=1)
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set_xlim(limits)
    axis.set_ylim(limits)
    axis.set_xlabel("fixed 125 ms odd-Qin RMS (Hz)")
    axis.set_ylabel("candidate odd-Qin RMS (Hz)")
    axis.set_title("D  Circles=fixed 500, triangles=adaptive; filled=evaluable")
    axis.grid(alpha=0.25, which="both")

    figure.suptitle(
        "Frozen H1–H7 result: INCONCLUSIVE — 5/55 tiles lacked a fresh exact GLRT epoch source\n"
        "All performance panels are post-hoc diagnostics on the 50 successful tiles\n"
        "No aggregate effect: H4/H5 independently fail support; H1/H2/H3/H6 are reindexed",
        fontsize=12.5,
    )
    figure.savefig(path, metadata={"Software": "Matplotlib"})


def _render_tracks(
    path: Path,
    payload: dict[str, object],
    forecasts: tuple[dict[str, object], ...],
    horizon_ms: float = TRACK_HORIZON_MS,
) -> None:
    labels = [str(value["capture_label"]) for value in payload["capture_intervals"]]
    figure = Figure(figsize=(16.0, 19.0), dpi=150, constrained_layout=True)
    axes = figure.subplots(len(labels), 2, squeeze=False)
    axes[0, 0].set_title(f"Future odd-Qin response and {horizon_ms:g} ms-ahead fits")
    axes[0, 1].set_title("Odd-Qin forecast residual")
    for index, label in enumerate(labels):
        selected = [
            row
            for row in forecasts
            if row["capture_label"] == label
            and float(row["horizon_ms"]) == horizon_ms
            and row["method"]
            in {holdout.METHOD_FIXED_125, holdout.METHOD_FIXED_500, holdout.METHOD_ADAPTIVE}
        ]
        left, right = axes[index]
        if not selected:
            for axis in (left, right):
                axis.text(0.5, 0.5, "no paired forecasts", ha="center", va="center")
                axis.set_xticks([])
                axis.set_yticks([])
            left.set_ylabel(label)
            continue
        baseline_rows = [row for row in selected if row["method"] == holdout.METHOD_FIXED_125]
        offset_hz = float(np.median([float(row["target_odd_cfo_hz"]) for row in baseline_rows]))
        tile_ids = sorted({str(row["tile_id"]) for row in selected})
        for tile_id in tile_ids:
            tile_baseline = [row for row in baseline_rows if row["tile_id"] == tile_id]
            if tile_baseline:
                left.scatter(
                    [float(row["target_time_s"]) for row in tile_baseline],
                    [float(row["target_odd_cfo_hz"]) - offset_hz for row in tile_baseline],
                    s=9,
                    color="#111827",
                    alpha=0.65,
                    label="future odd Qin" if tile_id == tile_ids[0] else None,
                    zorder=3,
                )
            for method, color, label_text in (
                (holdout.METHOD_FIXED_125, "#6b7280", "fixed 125 ms"),
                (holdout.METHOD_FIXED_500, "#2563eb", "fixed 500 ms"),
                (holdout.METHOD_ADAPTIVE, "#d97706", "adaptive"),
            ):
                rows = sorted(
                    [
                        row
                        for row in selected
                        if row["tile_id"] == tile_id and row["method"] == method
                    ],
                    key=lambda row: float(row["target_time_s"]),
                )
                if not rows:
                    continue
                left.plot(
                    [float(row["target_time_s"]) for row in rows],
                    [float(row["prediction_hz"]) - offset_hz for row in rows],
                    color=color,
                    linewidth=1.2,
                    label=label_text if tile_id == tile_ids[0] else None,
                )
                right.plot(
                    [float(row["target_time_s"]) for row in rows],
                    [float(row["odd_residual_hz"]) for row in rows],
                    color=color,
                    linewidth=1.0,
                    marker=".",
                    markersize=2.5,
                    label=label_text if tile_id == tile_ids[0] else None,
                )
        left.set_ylabel(f"{label}\nCFO − {offset_hz / 1_000:.1f} kHz (Hz)")
        right.axhline(0.0, color="#111827", linewidth=0.8)
        left.grid(alpha=0.2)
        right.grid(alpha=0.2)
        if index == len(labels) - 1:
            left.set_xlabel("recording-relative time (s)")
            right.set_xlabel("recording-relative time (s)")
        right.set_ylabel("residual (Hz)")
    figure.suptitle(
        f"Diagnostic {horizon_ms:g} ms forecasts; tile boundaries are never connected\n"
        "Past even Qin fits, future odd Qin responds; missing rows are retained as missingness\n"
        "H4/H5/H7 keep the frozen stride; H1/H2/H3/H6 are post-hoc reindexed",
        fontsize=12.5,
    )
    figure.legend(
        handles=[
            Line2D([], [], color="#111827", marker=".", linestyle="none", label="future odd Qin"),
            Line2D([], [], color="#6b7280", label="fixed 125 ms"),
            Line2D([], [], color="#2563eb", label="fixed 500 ms"),
            Line2D([], [], color="#d97706", label="adaptive"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.925),
        ncols=4,
        frameon=False,
        fontsize=8,
    )
    figure.savefig(path, metadata={"Software": "Matplotlib"})


def _write_csv(path: Path, rows: tuple[dict[str, object], ...]) -> None:
    if not rows:
        _atomic_write(path, b"")
        return
    fields = list(rows[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def run(
    *,
    input_root: Path,
    checkpoint_root: Path,
    replay_config_path: Path,
    holdout_path: Path,
    output_root: Path,
) -> dict[str, object]:
    _validate_output_root(input_root, checkpoint_root, output_root)
    verified = _load_verified_inputs(
        input_root,
        checkpoint_root,
        replay_config_path,
        holdout_path,
    )
    evaluation = holdout._evaluate_tiles(verified.replays, verified.config)
    decision = holdout._decision_status(evaluation.summaries, evaluation.coverage, verified.config)
    payload = _diagnostic_payload(verified, evaluation, decision)
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "diagnostic-summary.json"
    forecast_path = output_root / "diagnostic-forecast-rows.csv"
    comparison_path = output_root / "diagnostic-comparison.png"
    tracks_path = output_root / "diagnostic-tracks.png"
    manifest_path = output_root / "artifact-manifest.json"
    _atomic_write(summary_path, _json_bytes(payload))
    _write_csv(forecast_path, evaluation.forecasts)
    _render_comparison(comparison_path, payload)
    _render_tracks(tracks_path, payload, evaluation.forecasts)
    artifacts = {}
    for name, path in (
        ("summary", summary_path),
        ("forecast_rows", forecast_path),
        ("comparison", comparison_path),
        ("tracks", tracks_path),
    ):
        artifacts[name] = {
            "path": path.name,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
    manifest = {
        "schema": "org.leo.research.recent-adaptive-cfo-holdout-diagnostic-artifacts/v1",
        "primary_frozen_decision": "inconclusive",
        "diagnostic_only": True,
        "artifacts": artifacts,
    }
    _atomic_write(manifest_path, _json_bytes(manifest))
    return payload


def main() -> None:
    arguments = _arguments()
    result = run(
        input_root=arguments.input_root,
        checkpoint_root=arguments.checkpoint_root,
        replay_config_path=arguments.replay_config,
        holdout_path=arguments.holdout,
        output_root=arguments.output_root,
    )
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "completed_tile_count": result["completed_tile_count"],
                "failed_tile_count": result["failed_tile_count"],
                "forecast_row_count": result["forecast_row_count"],
                "output_root": str(arguments.output_root),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
