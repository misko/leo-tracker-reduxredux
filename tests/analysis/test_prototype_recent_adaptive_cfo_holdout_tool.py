from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from PIL import Image

ROOT = Path(__file__).parents[2]
CONFIG_PATH = ROOT / "config" / "analysis" / "recent-adaptive-cfo-holdout-replay-v1.json"
HOLDOUT_PATH = ROOT / "config" / "analysis" / "recent-adaptive-cfo-holdout-v1.json"


def _tool() -> ModuleType:
    path = ROOT / "tools" / "prototype_recent_adaptive_cfo_holdout.py"
    spec = importlib.util.spec_from_file_location(
        "prototype_recent_adaptive_cfo_holdout_tool",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _config() -> dict[str, Any]:
    return _object(CONFIG_PATH)


def _holdout() -> dict[str, Any]:
    return _object(HOLDOUT_PATH)


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_replay_config_is_closed_and_pins_the_unopened_holdout() -> None:
    tool = _tool()
    document = _config()

    assert tool._validate_config(copy.deepcopy(document)) == document
    assert document["holdout_input_sha256"] == _sha256(HOLDOUT_PATH)
    assert document["outcomes_opened_at_protocol_freeze"] is False
    assert document["history_durations_ms"] == [75.0, 125.0, 250.0, 500.0]
    assert document["fixed_history_durations_ms"] == [125.0, 500.0]
    assert document["forecast_horizons_ms"] == [125.0, 500.0, 1000.0]
    assert document["expected_labels"] == [f"H{index}" for index in range(1, 8)]

    mutations = []
    extra = copy.deepcopy(document)
    extra["unreviewed_option"] = True
    mutations.append(extra)
    opened = copy.deepcopy(document)
    opened["outcomes_opened_at_protocol_freeze"] = True
    mutations.append(opened)
    different_holdout = copy.deepcopy(document)
    different_holdout["holdout_input_sha256"] = "sha256:" + "0" * 64
    mutations.append(different_holdout)
    reordered = copy.deepcopy(document)
    reordered["expected_labels"] = list(reversed(reordered["expected_labels"]))
    mutations.append(reordered)
    tuned_history = copy.deepcopy(document)
    tuned_history["history_durations_ms"] = [75.0, 125.0, 250.0, 750.0]
    mutations.append(tuned_history)
    loosened_gate = copy.deepcopy(document)
    loosened_gate["decision"]["maximum_equal_capture_rms_ratio"] = 1.0
    mutations.append(loosened_gate)

    for mutation in mutations:
        with pytest.raises(
            ValueError,
            match="closed|frozen|holdout|outcome|unsupported|digest|changed|threshold",
        ):
            tool._validate_config(mutation)


def test_tiles_are_unique_equal_width_half_open_and_cover_every_frozen_interval() -> None:
    tool = _tool()
    document = tool._validate_config(_config())
    holdout = _holdout()
    all_ids: set[str] = set()

    for item in holdout["dwells"]:
        tiles = tool._plan_tiles(item, float(document["maximum_tile_duration_s"]))
        expected_count = math.ceil(
            (float(item["analysis_stop_s"]) - float(item["analysis_start_s"]))
            / float(document["maximum_tile_duration_s"])
        )
        assert len(tiles) == expected_count
        assert tiles == tool._plan_tiles(
            copy.deepcopy(item),
            float(document["maximum_tile_duration_s"]),
        )
        assert tiles[0].start_s == float(item["analysis_start_s"])
        assert tiles[-1].stop_s == float(item["analysis_stop_s"])
        assert [tile.tile_index for tile in tiles] == list(range(expected_count))
        assert all(tile.capture_label == item["label"] for tile in tiles)
        assert all(tile.start_s < tile.stop_s for tile in tiles)
        assert all(
            tile.stop_s - tile.start_s <= float(document["maximum_tile_duration_s"]) + 1e-12
            for tile in tiles
        )
        # A tile must contain the longest history plus the longest forecast.
        assert all(tile.stop_s - tile.start_s >= 1.5 for tile in tiles)
        assert all(
            left.stop_s == right.start_s for left, right in zip(tiles, tiles[1:], strict=False)
        )
        widths = [tile.stop_s - tile.start_s for tile in tiles]
        assert max(widths) - min(widths) <= 2e-12
        tile_ids = {tile.tile_id for tile in tiles}
        assert len(tile_ids) == len(tiles)
        assert not all_ids.intersection(tile_ids)
        all_ids.update(tile_ids)

    too_short_after_equal_split = copy.deepcopy(holdout["dwells"][0])
    too_short_after_equal_split.update({"analysis_start_s": 0.0, "analysis_stop_s": 2.9})
    with pytest.raises(ValueError, match="tile|span|history|forecast|short"):
        tool._plan_tiles(
            too_short_after_equal_split,
            float(document["maximum_tile_duration_s"]),
        )


def test_holdout_loader_verifies_frozen_digest_and_closed_identity(tmp_path: Path) -> None:
    tool = _tool()
    document = tool._validate_config(_config())

    loaded = tool._load_holdout(HOLDOUT_PATH, document)
    assert [item["label"] for item in loaded] == document["expected_labels"]
    assert len({item["session_id"] for item in loaded}) == len(loaded) == 7

    tampered_path = tmp_path / HOLDOUT_PATH.name
    tampered_path.write_bytes(HOLDOUT_PATH.read_bytes() + b" ")
    with pytest.raises(ValueError, match="holdout|digest|mismatch"):
        tool._load_holdout(tampered_path, document)


def _inventory(
    tile: Any,
    *,
    sample_rate_hz: int = 2_500_000,
    poison_odd: bool = False,
    even_offset_hz: float = 0.0,
) -> tuple[dict[str, object], ...]:
    rows = []
    start_sample = round(float(tile.start_s) * sample_rate_hz)
    maximum_frames = math.ceil((float(tile.stop_s) - float(tile.start_s)) * 750.0) + 2
    for tile_frame_index in range(maximum_frames):
        frame_start_sample = start_sample + round(tile_frame_index * sample_rate_hz / 750.0)
        if frame_start_sample >= round(float(tile.stop_s) * sample_rate_hz) - 5_000:
            break
        reference_time_s = (frame_start_sample + 1_672) / sample_rate_hz
        even_hz = (
            100_000.0
            + even_offset_hz
            - 1_800.0 * reference_time_s
            + 4.0 * math.sin(tile_frame_index * 0.37)
        )
        odd_hz = even_hz + 5.0 * math.cos(tile_frame_index * 0.21)
        if poison_odd:
            odd_hz += (1.0 if tile_frame_index % 2 else -1.0) * 1e12
        rows.append(
            {
                "continuity_safe": True,
                "even_absolute_cfo_hz": even_hz,
                "frame_index": tile_frame_index,
                "frame_start_sample": frame_start_sample,
                "label": tile.tile_id,
                "odd_absolute_cfo_hz": odd_hz,
                "reference_time_s": reference_time_s,
                "rejection_reasons": [],
                "training_supported": True,
            }
        )
    return tuple(rows)


def _tile_replay(tool: ModuleType, tile: Any, **inventory_options: object) -> Any:
    inventory = _inventory(tile, **inventory_options)
    return tool.TileReplay(
        tile=tile,
        frame_inventory=inventory,
        frame_epoch_sample=round(tile.start_s * 2_500_000) + 17,
        source_id=f"source:{tile.tile_id}",
        source_detection_time_s=0.5 * (tile.start_s + tile.stop_s),
        source_bound_cfo_hz=100_000.0,
        opportunity_count=len(inventory),
    )


def _evaluated(tool: ModuleType, replays: tuple[Any, ...]) -> tuple[Any, Any]:
    document = tool._validate_config(_config())
    prepared = tool._prepared_rows(replays)
    forecasts = []
    traces = []
    for replay in sorted(
        replays,
        key=lambda value: (value.tile.capture_label, value.tile.tile_index),
    ):
        rows = tool._tile_rows(replay, prepared)
        tracks = tool._build_tile_tracks(rows, document)
        tile_forecasts, _ = tool._forecast_tile(replay, rows, tracks, document)
        forecasts.extend(tile_forecasts)
        traces.extend(tool._rate_traces(replay, rows, tracks, document))
    return tuple(forecasts), tuple(traces)


def test_every_tile_rebinds_the_raw_source_and_epoch_independently(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = _tool()
    document = dict(tool._validate_config(_config()))
    holdout_document = _holdout()
    document.update(
        {
            "selection_reference_utc_ns": holdout_document["selection_reference_utc_ns"],
            "maximum_age_s": holdout_document["maximum_age_s"],
        }
    )
    item = _holdout()["dwells"][0]
    tiles = tool._plan_tiles(item, float(document["maximum_tile_duration_s"]))[:3]
    calls: list[tuple[float, float, int | None]] = []

    def fake_analyze_dwell(
        store: object,
        bulk_root: Path,
        tile_item: dict[str, Any],
        raw_document: dict[str, Any],
        *,
        maximum_frames: int | None,
    ) -> SimpleNamespace:
        assert store == "store"
        assert bulk_root == tmp_path
        assert (
            raw_document["selection_reference_utc_ns"] == _holdout()["selection_reference_utc_ns"]
        )
        calls.append(
            (
                float(tile_item["analysis_start_s"]),
                float(tile_item["analysis_stop_s"]),
                maximum_frames,
            )
        )
        midpoint = 0.5 * (
            float(tile_item["analysis_start_s"]) + float(tile_item["analysis_stop_s"])
        )
        return SimpleNamespace(
            label=tile_item["label"],
            analysis_start_s=tile_item["analysis_start_s"],
            analysis_stop_s=tile_item["analysis_stop_s"],
            frame_epoch_sample=round(midpoint * 2_500_000) + len(calls),
            source=SimpleNamespace(source_id=f"source-{len(calls)}", detection_time_s=midpoint),
            source_bound_cfo_hz=100_000.0 + len(calls),
            frame_inventory=(
                {
                    "continuity_safe": True,
                    "even_absolute_cfo_hz": 100_000.0,
                    "frame_index": 0,
                    "frame_start_sample": round(float(tile_item["analysis_start_s"]) * 2_500_000),
                    "label": tile_item["label"],
                    "odd_absolute_cfo_hz": 100_001.0,
                    "reference_time_s": float(tile_item["analysis_start_s"]),
                    "rejection_reasons": [],
                    "training_supported": True,
                },
            ),
            opportunity_count=1,
        )

    monkeypatch.setattr(tool, "_raw_analyze_dwell", fake_analyze_dwell)
    replays = tuple(tool._analyze_tile("store", tmp_path, item, tile, document) for tile in tiles)

    assert calls == [(tile.start_s, tile.stop_s, None) for tile in tiles]
    assert [replay.tile for replay in replays] == list(tiles)
    assert len({replay.frame_epoch_sample for replay in replays}) == len(tiles)
    assert len({replay.source_id for replay in replays}) == len(tiles)


def _rows_without_response(rows: tuple[dict[str, object], ...]) -> tuple[dict[str, object], ...]:
    response_fields = {"target_odd_cfo_hz", "odd_residual_hz"}
    return tuple(
        {key: value for key, value in row.items() if key not in response_fields} for row in rows
    )


def test_odd_response_poison_cannot_change_tracks_targets_or_method_availability() -> None:
    tool = _tool()
    document = tool._validate_config(_config())
    item = _holdout()["dwells"][0]
    tiles = tool._plan_tiles(item, float(document["maximum_tile_duration_s"]))[:2]
    ordinary_replays = tuple(_tile_replay(tool, tile) for tile in tiles)
    poisoned_replays = tuple(_tile_replay(tool, tile, poison_odd=True) for tile in tiles)

    ordinary_forecasts, ordinary_traces = _evaluated(tool, ordinary_replays)
    poisoned_forecasts, poisoned_traces = _evaluated(tool, poisoned_replays)

    assert ordinary_traces == poisoned_traces
    assert _rows_without_response(poisoned_forecasts) == _rows_without_response(ordinary_forecasts)
    assert [row["target_odd_cfo_hz"] for row in poisoned_forecasts] != [
        row["target_odd_cfo_hz"] for row in ordinary_forecasts
    ]


def test_tracker_history_and_forecasts_never_cross_tile_ids() -> None:
    tool = _tool()
    document = tool._validate_config(_config())
    item = _holdout()["dwells"][0]
    first, second = tool._plan_tiles(
        item,
        float(document["maximum_tile_duration_s"]),
    )[:2]
    ordinary = (_tile_replay(tool, first), _tile_replay(tool, second))
    changed_previous_tile = (
        _tile_replay(tool, first, even_offset_hz=1e9),
        _tile_replay(tool, second),
    )

    forecasts, traces = _evaluated(tool, ordinary)
    changed_forecasts, changed_traces = _evaluated(tool, changed_previous_tile)
    second_forecasts = tuple(row for row in forecasts if row["tile_id"] == second.tile_id)
    second_changed_forecasts = tuple(
        row for row in changed_forecasts if row["tile_id"] == second.tile_id
    )
    second_traces = tuple(row for row in traces if row["tile_id"] == second.tile_id)
    second_changed_traces = tuple(row for row in changed_traces if row["tile_id"] == second.tile_id)

    assert second_forecasts
    assert second_traces
    assert second_changed_forecasts == second_forecasts
    assert second_changed_traces == second_traces
    tile_start_sample = round(second.start_s * int(document["sample_rate_hz"]))
    for row in second_forecasts:
        assert int(row["training_stop_reference_sample"]) >= tile_start_sample
        assert int(row["target_reference_sample"]) < round(
            second.stop_s * int(document["sample_rate_hz"])
        )
        assert int(row["block_index"]) == math.floor(
            int(row["target_reference_sample"])
            / (int(document["sample_rate_hz"]) * float(document["aggregation_block_s"]))
        )
    assert all(row["tile_id"] == second.tile_id for row in second_traces)


def _summary_rows(tool: ModuleType) -> tuple[dict[str, object], ...]:
    rows = []
    # H1 deliberately has three responses in one recording-anchored block and
    # one response in another. Equal-block aggregation is sqrt((0^2 + 4^2)/2),
    # not the pooled 2 Hz RMS and not an equal-tile statistic.
    residuals = {
        "H1": (
            ("H1-tile-000", 10, 0.0),
            ("H1-tile-000", 10, 0.0),
            ("H1-tile-001", 10, 0.0),
            ("H1-tile-001", 11, 4.0),
        ),
        "H2": (("H2-tile-000", 20, 6.0),),
    }
    for capture_label, values in residuals.items():
        for target_index, (tile_id, block_index, residual) in enumerate(values):
            for method in tool.METHODS:
                rows.append(
                    {
                        "pair_id": f"{capture_label}:{target_index}:125ms",
                        "capture_label": capture_label,
                        "label": capture_label,
                        "tile_id": tile_id,
                        "training_tile_id": tile_id,
                        "method": method,
                        "horizon_ms": 125.0,
                        "block_index": block_index,
                        "target_reference_sample": block_index * 2_500_000 + target_index,
                        "target_time_s": float(block_index) + target_index / 10.0,
                        "cutoff_sample": 100 + target_index,
                        "training_stop_reference_sample": 100 + target_index,
                        "target_odd_cfo_hz": 100_000.0,
                        "odd_residual_hz": residual,
                        "rate_hz_s": -1_000.0,
                    }
                )
    return tuple(rows)


def _summary_lookup(
    rows: tuple[dict[str, object], ...],
    scope: str,
    label: str,
    method: str,
) -> dict[str, object]:
    selected = [
        row
        for row in rows
        if row["scope"] == scope
        and row["label"] == label
        and row["method"] == method
        and float(row["horizon_ms"]) == 125.0
    ]
    assert len(selected) == 1
    return selected[0]


def test_summaries_weight_recording_blocks_then_captures_not_tiles() -> None:
    tool = _tool()

    summaries = tool._summaries(_summary_rows(tool))
    h1 = _summary_lookup(summaries, "capture", "H1", tool.METHOD_FIXED_125)
    aggregate = _summary_lookup(
        summaries,
        "equal_capture",
        "ALL",
        tool.METHOD_FIXED_125,
    )

    assert h1["tile_count"] == 2
    assert h1["block_count"] == 2
    assert h1["odd_rms_hz"] == pytest.approx(2.0)
    assert h1["odd_block_equal_rms_hz"] == pytest.approx(math.sqrt(8.0))
    assert aggregate["capture_count"] == 2
    assert aggregate["odd_block_capture_equal_rms_hz"] == pytest.approx(math.sqrt(22.0))
    assert not any(row["scope"] == "tile" for row in summaries)


def _gate_fixture(
    tool: ModuleType,
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    summaries = []
    coverage = []
    labels = tuple(_config()["expected_labels"])
    horizons = tuple(float(value) for value in _config()["forecast_horizons_ms"])
    for horizon in horizons:
        for label in labels:
            for method, rms in (
                (tool.METHOD_FIXED_125, 100.0),
                (tool.METHOD_FIXED_500, 80.0),
                (tool.METHOD_ADAPTIVE, 90.0),
            ):
                summaries.append(
                    {
                        "scope": "capture",
                        "label": label,
                        "horizon_ms": horizon,
                        "method": method,
                        "target_count": 120,
                        "tile_count": 6,
                        "block_count": 6,
                        "odd_block_equal_rms_hz": rms,
                    }
                )
            coverage.append(
                {
                    "capture_label": label,
                    "horizon_ms": horizon,
                    "eligible_target_count": 120,
                    "paired_prediction_count": 120,
                    "paired_coverage": 1.0,
                    "nonempty_block_count": 6,
                }
            )
        for method, rms in (
            (tool.METHOD_FIXED_125, 100.0),
            (tool.METHOD_FIXED_500, 80.0),
            (tool.METHOD_ADAPTIVE, 90.0),
        ):
            summaries.append(
                {
                    "scope": "equal_capture",
                    "label": "ALL",
                    "horizon_ms": horizon,
                    "method": method,
                    "capture_count": len(labels),
                    "odd_block_capture_equal_rms_hz": rms,
                }
            )
    return tuple(summaries), tuple(coverage)


def test_decision_status_distinguishes_effect_failure_from_inconclusive_support() -> None:
    tool = _tool()
    document = tool._validate_config(_config())
    summaries, coverage = _gate_fixture(tool)

    advanced = tool._decision_status(summaries, coverage, document)
    assert advanced["status"] == "advance"
    assert advanced["support_failures"] == []
    assert all(row["passes"] is True for row in advanced["effect_results"])

    effect_failure = copy.deepcopy(list(summaries))
    regressed = next(
        row
        for row in effect_failure
        if row["scope"] == "capture"
        and row["label"] == "H3"
        and row["method"] == tool.METHOD_FIXED_500
        and float(row["horizon_ms"]) == 500.0
    )
    regressed["odd_block_equal_rms_hz"] = 106.0
    failed = tool._decision_status(tuple(effect_failure), coverage, document)
    assert failed["status"] == "scientific_fail"
    assert failed["support_failures"] == []

    insufficient_coverage = copy.deepcopy(list(coverage))
    insufficient_coverage[0]["paired_prediction_count"] = 99
    insufficient_coverage[0]["paired_coverage"] = 0.825
    inconclusive = tool._decision_status(summaries, tuple(insufficient_coverage), document)
    assert inconclusive["status"] == "inconclusive"
    assert inconclusive["support_failures"]

    missing_capture = tuple(row for row in summaries if row["label"] != "H7")
    missing = tool._decision_status(missing_capture, coverage, document)
    assert missing["status"] == "inconclusive"


def test_checkpoint_resume_is_digest_closed_and_never_silently_recomputes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = _tool()
    document = tool._validate_config(_config())
    item = _holdout()["dwells"][0]
    tile = tool._plan_tiles(item, float(document["maximum_tile_duration_s"]))[0]
    checkpoint_root = tmp_path / "checkpoints"
    calls = 0

    def fake_analyze_tile(
        store: object,
        bulk_root: Path,
        replay_item: dict[str, Any],
        replay_tile: Any,
        replay_document: dict[str, Any],
    ) -> Any:
        nonlocal calls
        calls += 1
        assert replay_item == item
        assert replay_tile == tile
        assert replay_document == document
        return _tile_replay(tool, tile)

    monkeypatch.setattr(tool, "_analyze_tile", fake_analyze_tile)
    first = tool._load_or_analyze_tile(
        checkpoint_root,
        "store",
        tmp_path,
        item,
        tile,
        document,
    )
    second = tool._load_or_analyze_tile(
        checkpoint_root,
        "store",
        tmp_path,
        item,
        tile,
        document,
    )
    assert second == first
    assert calls == 1

    checkpoint_files = sorted(checkpoint_root.rglob("*.json"))
    assert checkpoint_files
    tampered = _object(checkpoint_files[0])
    tampered["payload"]["source_bound_cfo_hz"] += 1.0
    checkpoint_files[0].write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="checkpoint|digest|bytes|mismatch"):
        tool._load_or_analyze_tile(
            checkpoint_root,
            "store",
            tmp_path,
            item,
            tile,
            document,
        )
    assert calls == 1


def test_checkpoint_rejects_analyzer_output_for_the_wrong_tile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = _tool()
    document = tool._validate_config(_config())
    item = _holdout()["dwells"][0]
    first, second = tool._plan_tiles(
        item,
        float(document["maximum_tile_duration_s"]),
    )[:2]
    monkeypatch.setattr(
        tool,
        "_analyze_tile",
        lambda *args, **kwargs: _tile_replay(tool, second),
    )

    with pytest.raises(ValueError, match="tile|identity|interval|mismatch"):
        tool._load_or_analyze_tile(
            tmp_path / "checkpoints",
            "store",
            tmp_path,
            item,
            first,
            document,
        )
    assert not list((tmp_path / "checkpoints").rglob("*.json"))


def test_all_frozen_tile_specs_round_trip_through_canonical_checkpoint_bytes() -> None:
    tool = _tool()
    config = dict(tool._validate_config(_config()))
    config["_replay_config_sha256"] = _sha256(CONFIG_PATH)
    dwells = tool._load_holdout(HOLDOUT_PATH, config)
    round_tripped_ids = []

    for item in dwells:
        for tile in tool._plan_tiles(item, float(config["maximum_tile_duration_s"])):
            midpoint_s = 0.5 * (tile.start_s + tile.stop_s)
            inventory = (
                {
                    "continuity_safe": True,
                    "even_absolute_cfo_hz": 100_000.0 + tile.tile_index,
                    "frame_index": 0,
                    "frame_start_sample": round(midpoint_s * int(config["sample_rate_hz"])),
                    "label": tile.tile_id,
                    "odd_absolute_cfo_hz": 100_001.0 + tile.tile_index,
                    "reference_time_s": midpoint_s,
                    "rejection_reasons": [],
                    "training_supported": True,
                },
            )
            replay = tool.TileReplay(
                tile=tile,
                frame_inventory=inventory,
                frame_epoch_sample=round(tile.start_s * int(config["sample_rate_hz"])) + 17,
                source_id=f"source:{tile.tile_id}",
                source_detection_time_s=midpoint_s,
                source_bound_cfo_hz=100_000.0 + tile.tile_index,
                opportunity_count=1,
            )
            wire_bytes = tool._json_bytes(tool._checkpoint_payload(replay, item, config))
            wire_document = json.loads(wire_bytes)
            recovered = tool._replay_from_checkpoint(wire_document, item, tile, config)

            assert wire_bytes == tool._json_bytes(wire_document)
            assert wire_document["payload"]["contract"]["tile"] == tool.stable_measurement_floats(
                {
                    "capture_label": tile.capture_label,
                    "tile_id": tile.tile_id,
                    "tile_index": tile.tile_index,
                    "start_s": tile.start_s,
                    "stop_s": tile.stop_s,
                }
            )
            assert recovered.tile == tile
            assert recovered.source_id == replay.source_id
            assert recovered.opportunity_count == len(recovered.frame_inventory) == 1
            assert wire_bytes == tool._json_bytes(tool._checkpoint_payload(recovered, item, config))
            round_tripped_ids.append(tile.tile_id)

    assert len(round_tripped_ids) == len(set(round_tripped_ids)) == 55


def test_bounded_smoke_cannot_overwrite_the_canonical_holdout_artifacts(tmp_path: Path) -> None:
    tool = _tool()
    canonical = ROOT / tool.DEFAULT_OUTPUT_ROOT

    with pytest.raises(ValueError, match="smoke|canonical|maximum.tiles|output"):
        tool.run(
            inputs_path=CONFIG_PATH,
            holdout_path=HOLDOUT_PATH,
            bulk_root=tmp_path / "bulk",
            checkpoint_root=tmp_path / "checkpoints",
            output_root=canonical,
            maximum_tiles=1,
        )


def test_json_and_csv_writers_are_byte_deterministic(tmp_path: Path) -> None:
    tool = _tool()
    left_json = tmp_path / "left.json"
    right_json = tmp_path / "right.json"
    left_csv = tmp_path / "left.csv"
    right_csv = tmp_path / "right.csv"
    value = {"schema": "example/v1", "rows": [{"b": 2.0, "a": 1}]}
    rows = (
        {"tile_id": "H1-T000", "method": tool.METHOD_FIXED_125, "residual_hz": 1.25},
        {"tile_id": "H1-T001", "method": tool.METHOD_FIXED_500, "residual_hz": -0.5},
    )

    left_json.write_bytes(tool._json_bytes(value))
    right_json.write_bytes(tool._json_bytes({"rows": value["rows"], "schema": value["schema"]}))
    tool._write_csv(left_csv, rows)
    tool._write_csv(right_csv, rows)

    assert left_json.read_bytes() == right_json.read_bytes()
    assert left_csv.read_bytes() == right_csv.read_bytes()
    assert left_csv.read_bytes().endswith(b"\n")


def _comparison_effects(tool: ModuleType) -> tuple[dict[str, object], ...]:
    rows = []
    labels = _config()["expected_labels"]
    for horizon_ms in _config()["forecast_horizons_ms"]:
        for method, ratio in (
            (tool.METHOD_FIXED_500, 0.8),
            (tool.METHOD_ADAPTIVE, 0.9),
        ):
            rows.append(
                {
                    "horizon_ms": horizon_ms,
                    "candidate_method": method,
                    "baseline_method": tool.METHOD_FIXED_125,
                    "equal_capture_rms_ratio": ratio,
                    "equal_capture_rms_change_percent": 100.0 * (1.0 - ratio),
                    "geometric_mean_per_capture_rms_ratio": ratio,
                    "worst_capture_ratio": ratio,
                    "per_capture_ratio": {label: ratio for label in labels},
                    "descriptive_gate_passes": ratio <= 0.9,
                }
            )
    return tuple(rows)


def test_matplotlib_holdout_comparison_is_byte_deterministic_under_reordering(
    tmp_path: Path,
) -> None:
    tool = _tool()
    summaries, coverage = _gate_fixture(tool)
    effects = _comparison_effects(tool)
    first_evaluation = tool.Evaluation((), (), summaries, coverage, effects)
    reversed_evaluation = tool.Evaluation(
        (),
        (),
        tuple(reversed(summaries)),
        tuple(reversed(coverage)),
        tuple(reversed(effects)),
    )
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"

    tool._render_comparison(first, first_evaluation, tool._validate_config(_config()))
    tool._render_comparison(second, reversed_evaluation, tool._validate_config(_config()))

    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(first) as image:
        assert image.format == "PNG"
        assert image.size[0] > image.size[1] > 1_000
        image.verify()


def _full_run_evaluation(tool: ModuleType) -> Any:
    summaries, coverage = _gate_fixture(tool)
    forecasts = tuple(
        {
            "pair_id": f"H1:synthetic:{method}",
            "capture_label": "H1",
            "tile_id": "H1-T000",
            "method": method,
            "horizon_ms": 125.0,
            "odd_residual_hz": float(index),
        }
        for index, method in enumerate(tool.METHODS)
    )
    traces = tuple(
        {
            "capture_label": label,
            "tile_id": f"{label}-T000",
            "method": method,
            "frame_start_sample": 1_000_000 + 10_000 * label_index,
            "reference_time_s": 1.0 + label_index,
            "selected_history_ms": 500.0 if method == tool.METHOD_FIXED_500 else 125.0,
            "rate_hz_s": -1_000.0 + 20.0 * method_index,
        }
        for label_index, label in enumerate(_config()["expected_labels"])
        for method_index, method in enumerate(tool.METHODS)
    )
    return tool.Evaluation(
        forecasts=forecasts,
        traces=traces,
        summaries=summaries,
        coverage=coverage,
        comparison_effects=_comparison_effects(tool),
    )


def test_mocked_full_run_enumerates_all_tiles_and_writes_digest_closed_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = _tool()
    config = tool._validate_config(_config())
    dwells = tool._load_holdout(HOLDOUT_PATH, config)
    planned = tuple(
        tile
        for item in dwells
        for tile in tool._plan_tiles(item, float(config["maximum_tile_duration_s"]))
    )
    calls: list[tuple[Path, str, str]] = []
    opened_roots: list[Path] = []
    closed_stores: list[object] = []

    class FakeStore:
        def close(self) -> None:
            closed_stores.append(self)

    def fake_open(root: object) -> FakeStore:
        opened_roots.append(Path(root.root))
        return FakeStore()

    def fake_load_or_analyze(
        checkpoint_root: Path,
        store: object,
        bulk_root: Path,
        item: dict[str, Any],
        tile: Any,
        replay_config: dict[str, Any],
    ) -> Any:
        assert isinstance(store, FakeStore)
        assert bulk_root == tmp_path / "bulk"
        assert item["label"] == tile.capture_label
        assert replay_config["holdout_input_sha256"] == config["holdout_input_sha256"]
        calls.append((checkpoint_root, str(item["label"]), tile.tile_id))
        checkpoint = tool._checkpoint_path(checkpoint_root, tile)
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_bytes(
            tool._json_bytes(
                {
                    "schema": "org.leo.test.synthetic-tile/v1",
                    "tile_id": tile.tile_id,
                }
            )
        )
        return tool.TileReplay(
            tile=tile,
            frame_inventory=(
                {
                    "label": tile.tile_id,
                    "training_supported": True,
                },
            ),
            frame_epoch_sample=round(tile.start_s * 2_500_000) + 17,
            source_id=f"source:{tile.tile_id}",
            source_detection_time_s=0.5 * (tile.start_s + tile.stop_s),
            source_bound_cfo_hz=100_000.0 + tile.tile_index,
            opportunity_count=1,
        )

    monkeypatch.setattr(tool, "RecordingStore", SimpleNamespace(open_pinned=fake_open))
    monkeypatch.setattr(tool, "PinnedLocalRoot", lambda path: SimpleNamespace(root=path))
    monkeypatch.setattr(tool, "_load_or_analyze_tile", fake_load_or_analyze)
    monkeypatch.setattr(
        tool, "_evaluate_tiles", lambda replays, document: _full_run_evaluation(tool)
    )

    output_roots = (tmp_path / "output-a", tmp_path / "output-b")
    checkpoint_roots = (tmp_path / "checkpoints-a", tmp_path / "checkpoints-b")
    results = []
    for output_root, checkpoint_root in zip(output_roots, checkpoint_roots, strict=True):
        results.append(
            tool.run(
                inputs_path=CONFIG_PATH,
                holdout_path=HOLDOUT_PATH,
                bulk_root=tmp_path / "bulk",
                checkpoint_root=checkpoint_root,
                output_root=output_root,
                maximum_tiles=None,
            )
        )

    assert len(planned) > len(dwells)
    assert len(calls) == 2 * len(planned)
    assert [tile_id for _, _, tile_id in calls[: len(planned)]] == [
        tile.tile_id for tile in planned
    ]
    assert [tile_id for _, _, tile_id in calls[len(planned) :]] == [
        tile.tile_id for tile in planned
    ]
    assert len(opened_roots) == len(closed_stores) == 2
    assert results[0] == results[1]
    assert results[0]["full_frozen_run"] is True
    assert results[0]["decision"]["status"] == "advance"
    assert results[0]["planned_tile_count"] == results[0]["completed_tile_count"] == len(planned)
    assert {row["tile"]["tile_id"] for row in results[0]["tile_replays"]} == {
        tile.tile_id for tile in planned
    }

    expected_outputs = {
        "artifact-manifest.json",
        "checkpoint-index.json",
        "comparison.png",
        "forecast-rows.csv",
        "rate-tracks.json",
        "summary.json",
        "tile-replays.json.gz",
    }
    for output_root, checkpoint_root in zip(output_roots, checkpoint_roots, strict=True):
        assert {path.name for path in output_root.iterdir()} == expected_outputs
        manifest = _object(output_root / "artifact-manifest.json")
        assert manifest["full_frozen_run"] is True
        assert set(manifest["artifacts"]) == {
            "checkpoint_index",
            "comparison_plot",
            "forecast_rows",
            "rate_tracks",
            "summary",
            "tile_replays",
        }
        for artifact in manifest["artifacts"].values():
            path = output_root / artifact["path"]
            assert path.stat().st_size == artifact["bytes"]
            assert _sha256(path) == artifact["sha256"]
        index = _object(output_root / "checkpoint-index.json")
        assert len(index["tiles"]) == len(planned)
        for tile_entry in index["tiles"]:
            checkpoint = checkpoint_root / tile_entry["path"]
            assert checkpoint.stat().st_size == tile_entry["bytes"]
            assert _sha256(checkpoint) == tile_entry["sha256"]
        with Image.open(output_root / "comparison.png") as image:
            assert image.format == "PNG"
            image.verify()
        with gzip.open(output_root / "tile-replays.json.gz", "rt", encoding="utf-8") as source:
            archive = json.load(source)
        assert archive["schema"] == "org.leo.research.recent-adaptive-cfo-tile-replays/v1"
        assert len(archive["tile_replays"]) == len(planned)
        assert {row["tile"]["tile_id"] for row in archive["tile_replays"]} == {
            tile.tile_id for tile in planned
        }

    for name in expected_outputs:
        assert (output_roots[0] / name).read_bytes() == (output_roots[1] / name).read_bytes()


def test_mocked_full_attempt_records_one_tile_failure_without_retry_or_substitution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = _tool()
    config = tool._validate_config(_config())
    dwells = tool._load_holdout(HOLDOUT_PATH, config)
    planned = tuple(
        tile
        for item in dwells
        for tile in tool._plan_tiles(item, float(config["maximum_tile_duration_s"]))
    )
    failed_tile = planned[17]
    called_ids: list[str] = []
    closed = False

    class FakeStore:
        def close(self) -> None:
            nonlocal closed
            closed = True

    def fake_load_or_analyze(
        checkpoint_root: Path,
        store: object,
        bulk_root: Path,
        item: dict[str, Any],
        tile: Any,
        replay_config: dict[str, Any],
    ) -> Any:
        del store, bulk_root, item, replay_config
        called_ids.append(tile.tile_id)
        if tile == failed_tile:
            raise ValueError("synthetic unsupported tile")
        checkpoint = tool._checkpoint_path(checkpoint_root, tile)
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_bytes(tool._json_bytes({"tile_id": tile.tile_id}))
        return tool.TileReplay(
            tile=tile,
            frame_inventory=(
                {
                    "label": tile.tile_id,
                    "training_supported": True,
                },
            ),
            frame_epoch_sample=round(tile.start_s * 2_500_000) + 17,
            source_id=f"source:{tile.tile_id}",
            source_detection_time_s=0.5 * (tile.start_s + tile.stop_s),
            source_bound_cfo_hz=100_000.0,
            opportunity_count=1,
        )

    monkeypatch.setattr(
        tool,
        "RecordingStore",
        SimpleNamespace(open_pinned=lambda root: FakeStore()),
    )
    monkeypatch.setattr(tool, "PinnedLocalRoot", lambda path: SimpleNamespace(root=path))
    monkeypatch.setattr(tool, "_load_or_analyze_tile", fake_load_or_analyze)
    monkeypatch.setattr(
        tool,
        "_evaluate_tiles",
        lambda *args, **kwargs: pytest.fail("an incomplete replay must not be evaluated"),
    )
    checkpoint_root = tmp_path / "checkpoints"
    output_root = tmp_path / "output"

    result = tool.run(
        inputs_path=CONFIG_PATH,
        holdout_path=HOLDOUT_PATH,
        bulk_root=tmp_path / "bulk",
        checkpoint_root=checkpoint_root,
        output_root=output_root,
        maximum_tiles=None,
    )

    assert called_ids == [tile.tile_id for tile in planned]
    assert called_ids.count(failed_tile.tile_id) == 1
    assert closed is True
    assert result["full_frozen_run"] is False
    assert result["full_frozen_attempt"] is True
    assert result["decision"]["status"] == "inconclusive"
    assert result["planned_tile_count"] == result["attempted_tile_count"] == len(planned)
    assert result["completed_tile_count"] == len(planned) - 1
    assert result["tile_failures"] == [
        {
            "tile": {
                "capture_label": failed_tile.capture_label,
                "tile_id": failed_tile.tile_id,
                "tile_index": failed_tile.tile_index,
                "start_s": failed_tile.start_s,
                "stop_s": failed_tile.stop_s,
            },
            "error_type": "ValueError",
            "reason": "synthetic unsupported tile",
        }
    ]
    assert {path.name for path in output_root.iterdir()} == {
        "artifact-manifest.json",
        "checkpoint-index.json",
        "summary.json",
        "tile-replays.json.gz",
    }
    manifest = _object(output_root / "artifact-manifest.json")
    assert manifest["full_frozen_run"] is False
    assert set(manifest["artifacts"]) == {"checkpoint_index", "summary", "tile_replays"}
    with gzip.open(output_root / "tile-replays.json.gz", "rt", encoding="utf-8") as source:
        archive = json.load(source)
    archived_ids = [row["tile"]["tile_id"] for row in archive["tile_replays"]]
    assert len(archived_ids) == len(planned) - 1
    assert failed_tile.tile_id not in archived_ids
    assert archived_ids == [tile.tile_id for tile in planned if tile != failed_tile]
    checkpoint_index = _object(output_root / "checkpoint-index.json")
    assert len(checkpoint_index["tiles"]) == len(planned) - 1


@pytest.mark.parametrize(
    ("checkpoint_root", "output_root"),
    (
        (Path("SAME"), Path("SAME")),
        (Path("SAFE-CHECKPOINT"), Path("/mnt/qnap01/codex-holdout-must-not-write")),
        (Path("/mnt/qnap01/codex-holdout-must-not-write"), Path("SAFE-OUTPUT")),
    ),
    ids=("same-root", "qnap-output", "qnap-checkpoint"),
)
def test_write_roots_fail_closed_before_opening_recording_store(
    checkpoint_root: Path,
    output_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = _tool()
    resolved_checkpoint = (
        tmp_path / checkpoint_root if not checkpoint_root.is_absolute() else checkpoint_root
    )
    resolved_output = tmp_path / output_root if not output_root.is_absolute() else output_root

    def forbidden_open(root: object) -> object:
        pytest.fail(f"unsafe roots reached RecordingStore.open_pinned: {root}")

    monkeypatch.setattr(tool, "RecordingStore", SimpleNamespace(open_pinned=forbidden_open))
    with pytest.raises(ValueError, match="checkpoint|output|QNAP|qnap|read.only|distinct"):
        tool.run(
            inputs_path=CONFIG_PATH,
            holdout_path=HOLDOUT_PATH,
            bulk_root=tmp_path / "bulk",
            checkpoint_root=resolved_checkpoint,
            output_root=resolved_output,
            maximum_tiles=None,
        )
