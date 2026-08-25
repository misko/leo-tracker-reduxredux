from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from PIL import Image

ROOT = Path(__file__).parents[2]
CONFIG_PATH = ROOT / "config" / "analysis" / "recent-adaptive-cfo-holdout-replay-v1.json"
HOLDOUT_PATH = ROOT / "config" / "analysis" / "recent-adaptive-cfo-holdout-v1.json"
REAL_DIAGNOSTIC_ROOT = (
    ROOT / "reports" / "figures" / "2026_08_25_recent_adaptive_cfo_holdout_diagnostic"
)
REAL_INCOMPLETE_ROOT = ROOT / "reports" / "figures" / "2026_08_25_recent_adaptive_cfo_holdout"
WARNING = "incomplete successful-tile diagnostic cannot advance, fail, tune, or promote"


def _module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _tool() -> ModuleType:
    return _module(
        ROOT / "tools" / "report_recent_adaptive_cfo_holdout_diagnostic.py",
        "report_recent_adaptive_cfo_holdout_diagnostic_tool",
    )


def _holdout_tool() -> ModuleType:
    return _module(
        ROOT / "tools" / "prototype_recent_adaptive_cfo_holdout.py",
        "prototype_recent_adaptive_cfo_holdout_for_diagnostic_tests",
    )


def _config() -> dict[str, Any]:
    value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _verified(tool: ModuleType) -> tuple[Any, Any, dict[str, Any]]:
    summary, dwells, planned_tiles, replays, evaluation, decision = _fixture()
    return (
        tool.VerifiedInputs(
            config=_config(),
            summary=summary,
            dwells=dwells,
            planned_tiles=planned_tiles,
            replays=replays,
            implementation_sha256={"holdout_tool": "sha256:" + "1" * 64},
            input_sha256={"tile_replays": "sha256:" + "2" * 64},
        ),
        evaluation,
        decision,
    )


def _fixture() -> tuple[
    dict[str, Any],
    tuple[dict[str, Any], ...],
    tuple[Any, ...],
    tuple[Any, ...],
    Any,
    dict[str, Any],
]:
    holdout = _holdout_tool()
    labels = tuple(f"H{index}" for index in range(1, 8))
    dwells = tuple(
        {
            "label": label,
            "session_id": f"session-{label}",
            "analysis_start_s": 0.0,
            "analysis_stop_s": 2.0,
        }
        for label in labels
    )
    planned_tiles = tuple(
        holdout.TileSpec(
            capture_label=label,
            tile_id=f"{label}-T000",
            tile_index=0,
            start_s=0.0,
            stop_s=2.0,
        )
        for label in labels
    )
    replays = tuple(
        holdout.TileReplay(
            tile=tile,
            frame_inventory=tuple({"training_supported": index < 5} for index in range(10)),
            frame_epoch_sample=1_000 * index,
            source_id=f"source:{tile.tile_id}",
            source_detection_time_s=1.0,
            source_bound_cfo_hz=100_000.0,
            opportunity_count=10,
        )
        for index, tile in enumerate(planned_tiles[:-1], start=1)
    )

    methods = (holdout.METHOD_FIXED_125, holdout.METHOD_FIXED_500, holdout.METHOD_ADAPTIVE)
    predictions = {
        holdout.METHOD_FIXED_125: (90.0, 188.0),
        holdout.METHOD_FIXED_500: (92.0, 190.0),
        holdout.METHOD_ADAPTIVE: (93.0, 191.0),
    }
    targets = (100.0, 200.0)
    forecasts = []
    for target_index, target_hz in enumerate(targets):
        target_sample = 1_500_000 + target_index * 37_500
        for method in methods:
            prediction_hz = predictions[method][target_index]
            forecasts.append(
                {
                    "pair_id": f"H1:H1-T000:{target_sample}:1250000samples",
                    "capture_label": "H1",
                    "tile_id": "H1-T000",
                    "training_tile_id": "H1-T000",
                    "method": method,
                    "horizon_ms": 500.0,
                    "block_index": target_index,
                    "capture_frame_index": 450 + target_index * 15,
                    "target_frame_start_sample": target_sample,
                    "target_reference_sample": target_sample + 1_672,
                    "target_time_s": 0.6 + target_index * 0.015,
                    "target_odd_cfo_hz": target_hz,
                    "cutoff_sample": target_sample - 1_250_000,
                    "training_cutoff_frame_start_sample": target_sample - 1_251_672,
                    "training_stop_reference_sample": target_sample - 1_250_000,
                    "training_stop_time_s": 0.1 + target_index * 0.015,
                    "actual_forecast_s": 0.5,
                    "selected_history_ms": 125.0 if method == holdout.METHOD_FIXED_125 else 500.0,
                    "cfo_hz_at_cutoff": prediction_hz + 50.0,
                    "rate_hz_s": -100.0,
                    "prediction_hz": prediction_hz,
                    "prediction_sigma_hz": 5.0,
                    "odd_residual_hz": target_hz - prediction_hz,
                }
            )

    summaries = tuple(
        {
            "scope": "capture",
            "label": "H1",
            "horizon_ms": 500.0,
            "method": method,
            "target_count": 2,
            "tile_count": 1,
            "block_count": 6,
            "odd_rms_hz": rms,
            "odd_block_equal_rms_hz": rms,
            "odd_median_absolute_hz": rms,
            "odd_bias_hz": rms,
        }
        for method, rms in (
            (holdout.METHOD_FIXED_125, 10.0),
            (holdout.METHOD_FIXED_500, 8.0),
            (holdout.METHOD_ADAPTIVE, 7.5),
        )
    )
    coverage = []
    for label in labels:
        for horizon_ms in (125.0, 500.0, 1_000.0):
            if label == "H1" and horizon_ms == 500.0:
                eligible, predicted, blocks = 125, 120, 6
            elif label == "H2" and horizon_ms == 500.0:
                eligible, predicted, blocks = 120, 100, 6
            else:
                eligible, predicted, blocks = 0, 0, 0
            coverage.append(
                {
                    "label": label,
                    "capture_label": label,
                    "horizon_ms": horizon_ms,
                    "eligible_target_count": eligible,
                    "paired_prediction_count": predicted,
                    "paired_coverage": predicted / eligible if eligible else 0.0,
                    "nonempty_block_count": blocks,
                }
            )
    effects = (
        {
            "horizon_ms": 500.0,
            "candidate_method": holdout.METHOD_FIXED_500,
            "baseline_method": holdout.METHOD_FIXED_125,
            "equal_capture_rms_ratio": 0.8,
            "equal_capture_rms_change_percent": 20.0,
            "worst_capture_ratio": 0.8,
            "per_capture_ratio": {"H1": 0.8},
        },
    )
    evaluation = holdout.Evaluation(
        forecasts=tuple(forecasts),
        traces=(),
        summaries=summaries,
        coverage=tuple(coverage),
        comparison_effects=effects,
    )
    source_decision = {
        "status": "inconclusive",
        "reason": "one or more frozen tiles failed provenance, continuity, or fresh binding",
    }
    summary = {
        "schema": "org.leo.research.recent-adaptive-cfo-holdout-summary/v1",
        "planned_tile_count": 7,
        "attempted_tile_count": 7,
        "completed_tile_count": 6,
        "full_frozen_attempt": True,
        "full_frozen_run": False,
        "configuration": _config(),
        "decision": source_decision,
        "tile_failures": [
            {
                "error_type": "ValueError",
                "reason": "selected interval has no exact branch-bound GLRT epoch source",
                "tile": {
                    "capture_label": "H7",
                    "tile_id": "H7-T000",
                    "tile_index": 0,
                    "start_s": 0.0,
                    "stop_s": 2.0,
                },
            }
        ],
    }
    counterfactual_decision = {
        "status": "advance",
        "reason": "successful tiles alone happen to satisfy numeric thresholds",
        "next_step": "must never escape a diagnostic namespace",
        "support_complete": True,
        "coverage_results": [
            {
                "capture_label": row["capture_label"],
                "horizon_ms": row["horizon_ms"],
                "passes": (
                    row["paired_coverage"] >= 0.9
                    and row["paired_prediction_count"] >= 100
                    and row["nonempty_block_count"] >= 5
                ),
            }
            for row in coverage
        ],
    }
    return (
        summary,
        dwells,
        planned_tiles,
        replays,
        evaluation,
        counterfactual_decision,
    )


def test_payload_preserves_inconclusive_source_decision_and_exact_support_accounting() -> None:
    tool = _tool()
    verified, evaluation, counterfactual_decision = _verified(tool)
    summary = verified.summary

    payload = tool._diagnostic_payload(
        verified,
        evaluation,
        counterfactual_decision,
    )

    assert payload["schema"] == "org.leo.research.recent-adaptive-cfo-holdout-diagnostic/v1"
    assert payload["diagnostic_only"] is True
    assert payload["decision"] == summary["decision"]
    assert payload["decision"]["status"] == "inconclusive"
    assert payload["promotion_claimed"] is False
    assert payload["full_frozen_run"] is False
    assert payload["claim_warning"] == WARNING
    assert payload["planned_tile_count"] == 7
    assert payload["completed_tile_count"] == 6
    assert payload["failed_tile_count"] == 1
    assert payload["forecast_row_count"] == 6
    assert len(payload["coverage"]) == 21
    adequate = next(
        row
        for row in payload["coverage"]
        if row["capture_label"] == "H1" and row["horizon_ms"] == 500.0
    )
    assert adequate == {
        "label": "H1",
        "capture_label": "H1",
        "horizon_ms": 500.0,
        "eligible_target_count": 125,
        "paired_prediction_count": 120,
        "paired_coverage": 120 / 125,
        "nonempty_block_count": 6,
    }
    sparse = next(
        row
        for row in payload["coverage"]
        if row["capture_label"] == "H2" and row["horizon_ms"] == 500.0
    )
    assert sparse["paired_prediction_count"] == 100
    assert sparse["paired_coverage"] == pytest.approx(5.0 / 6.0)
    assert sparse["nonempty_block_count"] == 6
    performance_adequate = next(
        row
        for row in payload["performance"]
        if row["capture_label"] == "H1" and row["horizon_ms"] == 500.0
    )
    performance_sparse = next(
        row
        for row in payload["performance"]
        if row["capture_label"] == "H2" and row["horizon_ms"] == 500.0
    )
    assert "frozen_support_gate_passes" not in performance_adequate
    assert "frozen_support_gate_passes" not in performance_sparse
    assert performance_adequate["numeric_support_status"] == "met_on_available_tiles"
    assert performance_adequate["capture_provenance_complete"] is True
    assert performance_adequate["cell_evaluable"] is True
    assert performance_sparse["numeric_support_status"] == "sparse"
    assert performance_sparse["capture_provenance_complete"] is True
    assert performance_sparse["cell_evaluable"] is False
    provenance_incomplete = next(
        row
        for row in payload["performance"]
        if row["capture_label"] == "H7" and row["horizon_ms"] == 500.0
    )
    assert provenance_incomplete["capture_provenance_complete"] is False
    assert provenance_incomplete["cell_evaluable"] is False

    assert payload["residual_definition"] == ("odd_residual_hz = target_odd_cfo_hz - prediction_hz")
    assert performance_adequate["fixed_125_rms_hz"] == 10.0
    assert performance_adequate["fixed_500_rms_hz"] == 8.0
    assert performance_adequate["fixed_500_over_125_ratio"] == 0.8
    assert performance_adequate["adaptive_rms_hz"] == 7.5
    assert performance_adequate["adaptive_over_125_ratio"] == 0.75
    assert payload["counterfactual_decision"]["status"] == "advance"
    assert payload["confirmatory_gate_evaluated"] is False
    assert payload["confirmatory_effect_gate_evaluated"] is False
    assert payload["aggregate_effect"] is None
    assert payload["paired_target_count"] == 2
    assert payload["adaptive_history_selection_counts"] == {"500": 2}
    assert "posthoc_target_mask" in payload["disclosures"]
    assert (
        "not the unavailable frozen full-run target mask"
        in payload["disclosures"]["posthoc_target_mask"]
    )


def test_payload_rejects_a_residual_that_does_not_equal_target_minus_prediction() -> None:
    tool = _tool()
    verified, evaluation, decision = _verified(tool)
    forecasts = list(evaluation.forecasts)
    forecasts[0] = {**forecasts[0], "odd_residual_hz": float(forecasts[0]["odd_residual_hz"]) + 1.0}
    tampered = type(evaluation)(
        forecasts=tuple(forecasts),
        traces=evaluation.traces,
        summaries=evaluation.summaries,
        coverage=evaluation.coverage,
        comparison_effects=evaluation.comparison_effects,
    )

    with pytest.raises(ValueError, match="residual|target.*prediction"):
        tool._diagnostic_payload(
            verified,
            tampered,
            decision,
        )


def test_plain_matplotlib_plots_are_byte_stable_and_do_not_mutate_the_payload(
    tmp_path: Path,
) -> None:
    tool = _tool()
    verified, evaluation, decision = _verified(tool)
    payload = tool._diagnostic_payload(
        verified,
        evaluation,
        decision,
    )
    before = copy.deepcopy(payload)
    first_comparison = tmp_path / "first-comparison.png"
    second_comparison = tmp_path / "second-comparison.png"
    first_tracks = tmp_path / "first-tracks.png"
    second_tracks = tmp_path / "second-tracks.png"

    tool._render_comparison(first_comparison, payload)
    tool._render_comparison(second_comparison, payload)
    tool._render_tracks(first_tracks, payload, evaluation.forecasts, horizon_ms=500.0)
    tool._render_tracks(second_tracks, payload, evaluation.forecasts, horizon_ms=500.0)

    assert payload == before
    assert first_comparison.read_bytes() == second_comparison.read_bytes()
    assert first_tracks.read_bytes() == second_tracks.read_bytes()
    assert _sha256(first_comparison) == _sha256(second_comparison)
    assert _sha256(first_tracks) == _sha256(second_tracks)
    with Image.open(first_comparison) as image:
        assert image.format == "PNG"
        assert image.width >= 1_000
        assert image.height >= 600
    with Image.open(first_tracks) as image:
        assert image.format == "PNG"
        assert image.width >= 1_000
        assert image.height >= 600


def test_track_plot_keeps_titles_global_legend_and_adaptive_when_h1_has_no_forecasts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = _tool()
    verified, evaluation, decision = _verified(tool)
    payload = tool._diagnostic_payload(verified, evaluation, decision)
    h2_forecasts = tuple({**row, "capture_label": "H2"} for row in evaluation.forecasts)
    captured = []

    monkeypatch.setattr(
        tool.Figure,
        "savefig",
        lambda figure, *args, **kwargs: captured.append(figure),
    )
    tool._render_tracks(tmp_path / "unused.png", payload, h2_forecasts, horizon_ms=500.0)

    assert len(captured) == 1
    figure = captured[0]
    assert figure.axes[0].get_title() == "Future odd-Qin response and 500 ms-ahead fits"
    assert figure.axes[1].get_title() == "Odd-Qin forecast residual"
    assert len(figure.legends) == 1
    legend_labels = {text.get_text() for text in figure.legends[0].get_texts()}
    assert legend_labels == {"future odd Qin", "fixed 125 ms", "fixed 500 ms", "adaptive"}
    assert any(line.get_label() == "adaptive" for axis in figure.axes for line in axis.lines)


def _checkpoint_fixture(
    tmp_path: Path,
) -> tuple[
    ModuleType,
    dict[str, Any],
    dict[str, dict[str, Any]],
    tuple[Any, ...],
    Path,
    Path,
]:
    holdout = _holdout_tool()
    config = holdout._validate_config(_config())
    config = {**config, "_replay_config_sha256": _sha256(CONFIG_PATH)}
    item = json.loads(HOLDOUT_PATH.read_text(encoding="utf-8"))["dwells"][0]
    tiles = holdout._plan_tiles(item, float(config["maximum_tile_duration_s"]))[:2]
    checkpoint_root = tmp_path / "checkpoints"
    checkpoint_root.mkdir()
    canonical_replays = []
    index_rows = []
    for index, tile in enumerate(tiles, start=1):
        midpoint_s = 0.5 * (tile.start_s + tile.stop_s)
        reference_time_s = tile.start_s + 0.01
        inventory = (
            {
                "continuity_safe": True,
                "even_absolute_cfo_hz": 100_000.0,
                "frame_index": 0,
                "frame_start_sample": round(reference_time_s * int(config["sample_rate_hz"])),
                "label": tile.tile_id,
                "odd_absolute_cfo_hz": 100_003.0,
                "reference_time_s": reference_time_s,
                "rejection_reasons": [],
                "training_supported": True,
            },
        )
        replay = holdout.TileReplay(
            tile=tile,
            frame_inventory=inventory,
            frame_epoch_sample=index,
            source_id=f"source:test:{index}",
            source_detection_time_s=midpoint_s,
            source_bound_cfo_hz=100_000.0,
            opportunity_count=1,
        )
        checkpoint_path = checkpoint_root / f"{tile.tile_id}.json"
        checkpoint_path.write_bytes(
            holdout._json_bytes(holdout._checkpoint_payload(replay, item, config))
        )
        canonical_replays.append(
            holdout._replay_from_checkpoint(
                json.loads(checkpoint_path.read_bytes()),
                item,
                tile,
                config,
            )
        )
        index_rows.append(
            {
                "tile_id": tile.tile_id,
                "path": checkpoint_path.name,
                "bytes": checkpoint_path.stat().st_size,
                "sha256": _sha256(checkpoint_path),
            }
        )
    index_path = tmp_path / "checkpoint-index.json"
    index_path.write_bytes(
        holdout._json_bytes(
            {
                "schema": "org.leo.research.recent-adaptive-cfo-checkpoint-index/v1",
                "tiles": index_rows,
            }
        )
    )
    return (
        holdout,
        config,
        {str(item["label"]): item},
        tuple(canonical_replays),
        checkpoint_root,
        index_path,
    )


def test_external_checkpoint_contract_and_digest_are_verified_without_opening_raw_iq(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = _tool()
    holdout, config, items, replays, checkpoint_root, index_path = _checkpoint_fixture(tmp_path)

    def raw_iq_forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("an archive-only diagnostic must never open raw IQ")

    monkeypatch.setattr(tool.holdout, "_raw_analyze_dwell", raw_iq_forbidden)
    implementation = tool._verify_checkpoints(
        checkpoint_root,
        index_path,
        items,
        replays,
        config,
    )

    expected = holdout._checkpoint_payload(replays[0], next(iter(items.values())), config)[
        "payload"
    ]["contract"]["implementation_sha256"]
    assert implementation == expected

    checkpoint_path = checkpoint_root / f"{replays[0].tile.tile_id}.json"
    checkpoint_path.write_bytes(checkpoint_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="checkpoint.*digest"):
        tool._verify_checkpoints(
            checkpoint_root,
            index_path,
            items,
            replays,
            config,
        )


def test_checkpoint_index_rejects_duplicate_id_that_omits_an_archived_tile(
    tmp_path: Path,
) -> None:
    tool = _tool()
    holdout, config, items, replays, checkpoint_root, index_path = _checkpoint_fixture(tmp_path)
    assert len(replays) == 2
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["tiles"][1] = copy.deepcopy(index["tiles"][0])
    index_path.write_bytes(holdout._json_bytes(index))

    with pytest.raises(ValueError, match="checkpoint.*(identit|unique|set|duplicate)"):
        tool._verify_checkpoints(
            checkpoint_root,
            index_path,
            items,
            replays,
            config,
        )


@pytest.mark.parametrize("mutation", ("geometry", "error_type"))
def test_input_loader_rejects_a_failure_record_that_does_not_match_the_frozen_tile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutation: str,
) -> None:
    tool = _tool()
    input_root = tmp_path / "incomplete"
    shutil.copytree(REAL_INCOMPLETE_ROOT, input_root)
    summary_path = input_root / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    failure = summary["tile_failures"][0]
    if mutation == "geometry":
        failure["tile"]["start_s"] = float(failure["tile"]["start_s"]) + 0.001
    else:
        failure["error_type"] = "RuntimeError"
    summary_path.write_bytes(tool._json_bytes(summary))
    manifest_path = input_root / "artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["summary"].update(
        {
            "bytes": summary_path.stat().st_size,
            "sha256": _sha256(summary_path),
        }
    )
    manifest_path.write_bytes(tool._json_bytes(manifest))
    monkeypatch.setattr(
        tool,
        "_verify_checkpoints",
        lambda *args: {"holdout_tool": "sha256:" + "1" * 64},
    )
    monkeypatch.setattr(
        tool.holdout,
        "_raw_analyze_dwell",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("input verification attempted to open raw IQ")
        ),
    )

    with pytest.raises(ValueError, match="fail|tile|geometry|identity|error"):
        tool._load_verified_inputs(
            input_root,
            tmp_path / "unused-checkpoints",
            CONFIG_PATH,
            HOLDOUT_PATH,
        )


def test_run_is_byte_stable_emits_exact_residuals_and_digest_closes_every_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = _tool()
    verified, evaluation, diagnostic_decision = _verified(tool)
    assert diagnostic_decision["status"] == "advance"
    input_root = tmp_path / "input"
    checkpoint_root = tmp_path / "checkpoints"
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    input_root.mkdir()
    checkpoint_root.mkdir()
    calls = []

    def load_verified_inputs(
        actual_input_root: Path,
        actual_checkpoint_root: Path,
        actual_replay_config_path: Path,
        actual_holdout_path: Path,
    ) -> Any:
        calls.append(
            (
                actual_input_root,
                actual_checkpoint_root,
                actual_replay_config_path,
                actual_holdout_path,
            )
        )
        return verified

    monkeypatch.setattr(tool, "_load_verified_inputs", load_verified_inputs)
    monkeypatch.setattr(tool.holdout, "_evaluate_tiles", lambda *args: evaluation)
    monkeypatch.setattr(tool.holdout, "_decision_status", lambda *args: diagnostic_decision)
    monkeypatch.setattr(
        tool.holdout,
        "_raw_analyze_dwell",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("diagnostic run attempted to open raw IQ")
        ),
    )

    first = tool.run(
        input_root=input_root,
        checkpoint_root=checkpoint_root,
        replay_config_path=CONFIG_PATH,
        holdout_path=HOLDOUT_PATH,
        output_root=first_root,
    )
    second = tool.run(
        input_root=input_root,
        checkpoint_root=checkpoint_root,
        replay_config_path=CONFIG_PATH,
        holdout_path=HOLDOUT_PATH,
        output_root=second_root,
    )

    expected_names = {
        "diagnostic-summary.json",
        "diagnostic-forecast-rows.csv",
        "diagnostic-comparison.png",
        "diagnostic-tracks.png",
        "artifact-manifest.json",
    }
    assert {path.name for path in first_root.iterdir()} == expected_names
    assert {path.name for path in second_root.iterdir()} == expected_names
    assert first == second
    assert first["decision"]["status"] == "inconclusive"
    assert first["counterfactual_decision"]["status"] == "advance"
    assert first["confirmatory_gate_evaluated"] is False
    assert first["promotion_claimed"] is False
    assert len(calls) == 2
    for name in expected_names:
        assert (first_root / name).read_bytes() == (second_root / name).read_bytes()

    manifest = json.loads((first_root / "artifact-manifest.json").read_text(encoding="utf-8"))
    assert manifest["primary_frozen_decision"] == "inconclusive"
    assert manifest["diagnostic_only"] is True
    assert {row["path"] for row in manifest["artifacts"].values()} == expected_names - {
        "artifact-manifest.json"
    }
    for row in manifest["artifacts"].values():
        path = first_root / row["path"]
        assert row["bytes"] == path.stat().st_size
        assert row["sha256"] == _sha256(path)

    with (first_root / "diagnostic-forecast-rows.csv").open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == len(evaluation.forecasts)
    for row in rows:
        assert float(row["odd_residual_hz"]) == pytest.approx(
            float(row["target_odd_cfo_hz"]) - float(row["prediction_hz"]),
            abs=1e-12,
        )


def test_real_archive_only_diagnostic_pins_support_missingness_and_residual_counts() -> None:
    summary_path = REAL_DIAGNOSTIC_ROOT / "diagnostic-summary.json"
    forecast_path = REAL_DIAGNOSTIC_ROOT / "diagnostic-forecast-rows.csv"
    manifest_path = REAL_DIAGNOSTIC_ROOT / "artifact-manifest.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert summary["decision"]["status"] == "inconclusive"
    assert summary["diagnostic_only"] is True
    assert summary["promotion_claimed"] is False
    assert summary["full_frozen_run"] is False
    assert summary["claim_warning"] == WARNING
    assert summary["planned_tile_count"] == 55
    assert summary["completed_tile_count"] == 50
    assert summary["failed_tile_count"] == 5
    assert summary["forecast_row_count"] == 4_248
    assert summary["aggregate_effect"] is None
    assert "posthoc_target_mask" in summary["disclosures"]

    expected_counts = {
        ("H1", 125.0): (1, 0, 0),
        ("H1", 500.0): (0, 0, 0),
        ("H1", 1_000.0): (0, 0, 0),
        ("H2", 125.0): (295, 293, 12),
        ("H2", 500.0): (182, 179, 11),
        ("H2", 1_000.0): (63, 63, 6),
        ("H3", 125.0): (100, 100, 8),
        ("H3", 500.0): (11, 11, 3),
        ("H3", 1_000.0): (0, 0, 0),
        ("H4", 125.0): (8, 8, 4),
        ("H4", 500.0): (0, 0, 0),
        ("H4", 1_000.0): (0, 0, 0),
        ("H5", 125.0): (18, 7, 4),
        ("H5", 500.0): (0, 0, 0),
        ("H5", 1_000.0): (0, 0, 0),
        ("H6", 125.0): (70, 38, 11),
        ("H6", 500.0): (50, 13, 6),
        ("H6", 1_000.0): (18, 7, 3),
        ("H7", 125.0): (352, 352, 11),
        ("H7", 500.0): (239, 238, 8),
        ("H7", 1_000.0): (108, 107, 7),
    }
    observed_counts = {
        (str(row["capture_label"]), float(row["horizon_ms"])): (
            int(row["eligible_target_count"]),
            int(row["paired_prediction_count"]),
            int(row["nonempty_block_count"]),
        )
        for row in summary["coverage"]
    }
    assert observed_counts == expected_counts

    performance = summary["performance"]
    assert len(performance) == 21
    assert Counter(row["numeric_support_status"] for row in performance) == {
        "met_on_available_tiles": 6,
        "sparse": 15,
    }
    assert {row["capture_label"] for row in performance if row["capture_provenance_complete"]} == {
        "H4",
        "H5",
        "H7",
    }
    evaluable = [row for row in performance if row["cell_evaluable"]]
    assert len(evaluable) == 3
    assert {row["capture_label"] for row in evaluable} == {"H7"}
    assert all(
        row["numeric_support_status"] == "sparse"
        for row in performance
        if row["capture_label"] in {"H4", "H5"}
    )
    available = [row for row in performance if row["available"]]
    assert len(available) == 13
    assert all(float(row["fixed_500_over_125_ratio"]) < 1.0 for row in available)

    methods_by_pair: dict[str, set[str]] = defaultdict(set)
    adaptive_histories: Counter[float] = Counter()
    with forecast_path.open(encoding="utf-8", newline="") as source:
        forecasts = list(csv.DictReader(source))
    assert len(forecasts) == 4_248
    for row in forecasts:
        methods_by_pair[row["pair_id"]].add(row["method"])
        assert float(row["odd_residual_hz"]) == (
            float(row["target_odd_cfo_hz"]) - float(row["prediction_hz"])
        )
        if row["method"] == "adaptive_75_500ms":
            adaptive_histories[float(row["selected_history_ms"])] += 1
    assert len(methods_by_pair) == 1_416
    assert all(
        methods == {"fixed_125ms", "fixed_500ms", "adaptive_75_500ms"}
        for methods in methods_by_pair.values()
    )
    assert adaptive_histories == {75.0: 61, 125.0: 169, 250.0: 174, 500.0: 1_012}

    assert manifest["primary_frozen_decision"] == "inconclusive"
    assert manifest["diagnostic_only"] is True
    for row in manifest["artifacts"].values():
        path = REAL_DIAGNOSTIC_ROOT / row["path"]
        assert row["bytes"] == path.stat().st_size
        assert row["sha256"] == _sha256(path)
