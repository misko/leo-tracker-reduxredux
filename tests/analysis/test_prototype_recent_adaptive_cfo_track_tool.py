from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from PIL import Image

ROOT = Path(__file__).parents[2]
UPSTREAM_ROOT = ROOT / "reports" / "figures" / "2026_08_25_recent_frame_cfo_rate"
CONFIG_PATH = ROOT / "config" / "analysis" / "recent-adaptive-cfo-track-v1.json"
HOLDOUT_PATH = ROOT / "config" / "analysis" / "recent-adaptive-cfo-holdout-v1.json"


def _tool() -> ModuleType:
    path = ROOT / "tools" / "prototype_recent_adaptive_cfo_track.py"
    spec = importlib.util.spec_from_file_location(
        "prototype_recent_adaptive_cfo_track_tool",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _json_bytes(document: object) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()


def _copy_upstream(tmp_path: Path) -> Path:
    destination = tmp_path / "upstream"
    shutil.copytree(UPSTREAM_ROOT, destination)
    return destination


def _config(*, labels: tuple[str, ...] = ("D1", "D2")) -> dict[str, Any]:
    document = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    document.update(
        {
            "labels": list(labels),
            "target_stride_frames": 1,
            "minimum_frames": 3,
            "minimum_effective_frames": 3,
            "minimum_history_coverage": 0.8,
            "maximum_gap_ms": 12.0,
        }
    )
    return document


def _inventory(
    *,
    labels: tuple[str, ...] = ("D1", "D2"),
    poison_odd: bool = False,
    training_gap: bool = False,
) -> tuple[dict[str, object], ...]:
    rows = []
    for label_index, label in enumerate(labels):
        for frame_index in range(171):
            relative_time_s = frame_index * 0.010
            continuity_safe = not (training_gap and 61 <= frame_index <= 66)
            even_hz = (
                100_000.0
                + 500.0 * label_index
                - 1_800.0 * relative_time_s
                + 30.0 * relative_time_s**2
                + 3.0 * math.sin(frame_index * 0.7)
            )
            odd_hz = even_hz + 7.0 * math.cos(frame_index * 0.37)
            if poison_odd:
                odd_hz += (-1.0 if frame_index % 2 else 1.0) * 1e12
            rows.append(
                {
                    "continuity_safe": continuity_safe,
                    "even_absolute_cfo_hz": even_hz,
                    "frame_index": frame_index,
                    "frame_start_sample": frame_index * 25_000,
                    "label": label,
                    "odd_absolute_cfo_hz": odd_hz,
                    "reference_time_s": 10.0 + relative_time_s,
                    "rejection_reasons": ([] if continuity_safe else ["continuity_unsafe"]),
                    "training_supported": continuity_safe,
                }
            )
    return tuple(rows)


def _manifest_sha256(root: Path) -> str:
    return _sha256((root / "artifact-manifest.json").read_bytes())


def _rewrite_artifact(root: Path, artifact_name: str, transform: Any) -> str:
    manifest_path = root / "artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact = manifest["artifacts"][artifact_name]
    path = root / artifact["path"]
    document = json.loads(path.read_text(encoding="utf-8"))
    transform(document)
    payload = _json_bytes(document)
    path.write_bytes(payload)
    artifact.update({"bytes": len(payload), "sha256": _sha256(payload)})
    manifest_path.write_bytes(_json_bytes(manifest))
    return _manifest_sha256(root)


def test_verified_upstream_inherits_exact_recent_provenance_and_labels(
    tmp_path: Path,
) -> None:
    tool = _tool()
    upstream = _copy_upstream(tmp_path)

    summary, inventory, manifest = tool._load_verified_upstream(
        upstream,
        _manifest_sha256(upstream),
    )

    assert summary["schema"] == "org.leo.research.recent-frame-cfo-rate-summary/v1"
    assert summary["maximum_age_s"] == 43_200.0
    assert summary["selection_reference_utc"] == "2026-08-25T16:43:13+00:00"
    assert [row["label"] for row in summary["dwells"]] == ["D1", "D2", "D3"]
    assert {row["label"] for row in inventory} == {"D1", "D2", "D3"}
    assert max(float(row["age_s"]) for row in summary["dwells"]) <= 43_200.0
    assert manifest["artifacts"]["summary"]["sha256"] == _sha256(
        (upstream / "summary.json").read_bytes()
    )


def test_holdout_freeze_is_seven_unique_unexamined_long_tracks() -> None:
    document = json.loads(HOLDOUT_PATH.read_text(encoding="utf-8"))

    assert set(document) == {
        "schema",
        "selection_reference_utc_ns",
        "maximum_age_s",
        "selection_basis",
        "frame_cfo_outcomes_examined_at_freeze",
        "required_replay_policy",
        "dwells",
    }
    assert document["schema"] == "org.leo.research.recent-adaptive-cfo-holdout/v1"
    assert document["selection_reference_utc_ns"] == 1_787_676_193_000_000_000
    assert document["maximum_age_s"] == 43_200.0
    assert document["frame_cfo_outcomes_examined_at_freeze"] is False
    assert [row["label"] for row in document["dwells"]] == [f"H{index}" for index in range(1, 8)]
    assert len({row["session_id"] for row in document["dwells"]}) == 7
    assert all(
        row["analysis_stop_s"] - row["analysis_start_s"] >= 10.0 for row in document["dwells"]
    )


def test_upstream_loader_fails_closed_on_manifest_or_file_digest_mismatch(
    tmp_path: Path,
) -> None:
    tool = _tool()
    upstream = _copy_upstream(tmp_path)
    expected = _manifest_sha256(upstream)

    with pytest.raises(ValueError, match="manifest.*digest|digest.*manifest"):
        tool._load_verified_upstream(upstream, "sha256:" + "0" * 64)

    summary_path = upstream / "summary.json"
    summary_path.write_bytes(summary_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="summary|artifact|digest|bytes"):
        tool._load_verified_upstream(upstream, expected)


@pytest.mark.parametrize("kind", ("summary-field", "row-field", "too-old"))
def test_upstream_loader_fails_closed_on_schema_row_or_age_drift(
    tmp_path: Path,
    kind: str,
) -> None:
    tool = _tool()
    upstream = _copy_upstream(tmp_path)

    if kind == "summary-field":
        expected = _rewrite_artifact(
            upstream,
            "summary",
            lambda document: document.update({"unreviewed_selection": True}),
        )
    elif kind == "row-field":
        expected = _rewrite_artifact(
            upstream,
            "frame_inventory",
            lambda document: document[0].update({"unreviewed_response": 1.0}),
        )
    else:
        expected = _rewrite_artifact(
            upstream,
            "summary",
            lambda document: document.update({"maximum_age_s": math.nextafter(43_200.0, math.inf)}),
        )

    with pytest.raises(ValueError, match="unsupported|closed|schema|field|12.hour|age"):
        tool._load_verified_upstream(upstream, expected)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("history_durations_ms", [75.0, 125.0, 500.0]),
        ("history_durations_ms", [75.0, 125.0, 125.0, 500.0]),
        ("fixed_history_durations_ms", [125.0, 250.0]),
        ("forecast_horizons_ms", [20.0, 0.0, 500.0]),
        ("forecast_horizons_ms", [20.0, 125.0, 1_000.0001]),
        ("forecast_horizons_ms", [125.0, 20.0]),
    ),
)
def test_config_rejects_nonfrozen_histories_and_bad_horizons(
    field: str,
    value: list[float],
) -> None:
    tool = _tool()
    document = _config()
    document[field] = value

    with pytest.raises(ValueError, match="histor|fixed|horizon|positive|increasing"):
        tool._validate_config(document)


def test_odd_qin_poison_cannot_change_tracks_or_history_selection() -> None:
    tool = _tool()
    document = tool._validate_config(_config())
    ordinary = _inventory()
    poisoned = _inventory(poison_odd=True)

    ordinary_tracks = tool._build_tracks(ordinary, document)
    poisoned_tracks = tool._build_tracks(poisoned, document)

    assert poisoned_tracks == ordinary_tracks
    ordinary_rows = tool._forecast_rows(ordinary, ordinary_tracks, document)
    poisoned_rows = tool._forecast_rows(poisoned, poisoned_tracks, document)
    nonresponse_fields = tuple(
        field for field in ordinary_rows[0] if field not in {"target_odd_cfo_hz", "odd_residual_hz"}
    )
    assert [tuple(row[field] for field in nonresponse_fields) for row in poisoned_rows] == [
        tuple(row[field] for field in nonresponse_fields) for row in ordinary_rows
    ]


def test_forecasts_are_strictly_causal_exact_and_three_way_paired() -> None:
    tool = _tool()
    document = tool._validate_config(_config())
    inventory = _inventory()
    rows = tool._forecast_rows(inventory, tool._build_tracks(inventory, document), document)

    assert rows
    methods_by_pair: dict[str, set[str]] = defaultdict(set)
    target_by_pair: dict[str, tuple[object, ...]] = {}
    for row in rows:
        methods_by_pair[str(row["pair_id"])].add(str(row["method"]))
        identity = (
            row["label"],
            row["horizon_ms"],
            row["target_frame_index"],
            row["target_frame_start_sample"],
            row["target_time_s"],
            row["target_odd_cfo_hz"],
        )
        assert target_by_pair.setdefault(str(row["pair_id"]), identity) == identity
        assert int(row["training_stop_reference_sample"]) <= int(row["cutoff_sample"])
        assert float(row["actual_forecast_s"]) == pytest.approx(
            (int(row["target_reference_sample"]) - int(row["training_stop_reference_sample"]))
            / int(document["sample_rate_hz"])
        )
        expected_prediction = float(row["cfo_hz_at_cutoff"]) + float(row["rate_hz_s"]) * float(
            row["actual_forecast_s"]
        )
        assert float(row["prediction_hz"]) == pytest.approx(expected_prediction)
        assert float(row["odd_residual_hz"]) == pytest.approx(
            float(row["target_odd_cfo_hz"]) - expected_prediction
        )

    assert all(methods == set(tool.METHODS) for methods in methods_by_pair.values())


def test_continuity_boundary_resets_each_tracker_and_cannot_be_forecast_across() -> None:
    tool = _tool()
    document = tool._validate_config(_config(labels=("D1", "D2")))
    inventory = _inventory(training_gap=True)
    tracks = tool._build_tracks(inventory, document)

    for label_tracks in tracks.values():
        for track in label_tracks.values():
            post_gap = next(
                estimate
                for estimate in track.estimates
                if estimate.frame_start_sample == 67 * 25_000
            )
            assert post_gap.reference_time_s == pytest.approx(10.67)
            assert post_gap.reset_reason.value == "continuity_segment_changed"
            assert post_gap.cfo_hz is None

    rows = tool._forecast_rows(inventory, tracks, document)
    crossing = [
        row
        for row in rows
        if int(row["target_frame_start_sample"]) >= 67 * 25_000
        and int(row["training_cutoff_frame_start_sample"]) <= 60 * 25_000
    ]
    assert crossing == []


def _summary_rows(tool: ModuleType) -> tuple[dict[str, object], ...]:
    rows = []
    # D1 deliberately has unequal frame counts in its two blocks.  Equal-block
    # aggregation must produce sqrt(mean((0^2, 4^2))) = sqrt(8), not a pooled RMS.
    residuals = {
        "D1": ((0, 0.0), (0, 0.0), (0, 0.0), (1, 4.0)),
        "D2": ((0, 6.0),),
    }
    for label, values in residuals.items():
        for target_index, (block_index, residual) in enumerate(values):
            for method in tool.METHODS:
                rows.append(
                    {
                        "pair_id": f"{label}:{target_index}:20ms",
                        "label": label,
                        "method": method,
                        "horizon_ms": 20.0,
                        "block_index": block_index,
                        "target_time_s": 1.0 + target_index * 0.02,
                        "cutoff_sample": 100 + target_index,
                        "training_stop_reference_sample": 100 + target_index,
                        "odd_residual_hz": residual,
                        "rate_hz_s": -1_000.0,
                    }
                )
    return tuple(rows)


def test_summaries_weight_recording_blocks_then_dwells_equally() -> None:
    tool = _tool()

    summaries = tool._summaries(_summary_rows(tool))

    d1 = tool._summary_lookup(
        summaries,
        "dwell",
        "D1",
        20.0,
        tool.METHOD_FIXED_125,
    )
    aggregate = tool._summary_lookup(
        summaries,
        "equal_dwell",
        "ALL",
        20.0,
        tool.METHOD_FIXED_125,
    )
    assert d1["odd_block_equal_rms_hz"] == pytest.approx(math.sqrt(8.0))
    assert d1["odd_rms_hz"] == pytest.approx(2.0)
    assert aggregate["odd_block_equal_rms_hz"] == pytest.approx(math.sqrt(22.0))


def _plot_fixture(
    tool: ModuleType,
) -> tuple[dict[str, Any], tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    document = _config()
    document["forecast_horizons_ms"] = [20.0, 125.0]
    summaries = []
    for horizon_index, horizon in enumerate(document["forecast_horizons_ms"]):
        for method_index, method in enumerate(tool.METHODS):
            summaries.append(
                {
                    "scope": "equal_dwell",
                    "label": "ALL",
                    "horizon_ms": horizon,
                    "method": method,
                    "odd_block_equal_rms_hz": 20.0 + horizon_index + method_index,
                }
            )
            for label_index, label in enumerate(document["labels"]):
                summaries.append(
                    {
                        "scope": "dwell",
                        "label": label,
                        "horizon_ms": horizon,
                        "method": method,
                        "odd_block_equal_rms_hz": (
                            18.0 + horizon_index + method_index + label_index
                        ),
                    }
                )
    traces = []
    for label_index, label in enumerate(document["labels"]):
        for method_index, method in enumerate(tool.METHODS):
            for index in range(4):
                traces.append(
                    {
                        "label": label,
                        "method": method,
                        "reference_time_s": 10.0 + index * 0.02,
                        "selected_history_ms": (75.0, 125.0, 250.0, 500.0)[index],
                        "rate_hz_s": -1_500.0 + 20.0 * method_index + label_index,
                    }
                )
    return document, tuple(summaries), tuple(traces)


def test_matplotlib_comparison_is_byte_deterministic_under_reversed_inputs(
    tmp_path: Path,
) -> None:
    tool = _tool()
    document, summaries, traces = _plot_fixture(tool)
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"

    tool._render_comparison(first, summaries, traces, document)
    tool._render_comparison(second, tuple(reversed(summaries)), tuple(reversed(traces)), document)

    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(first) as image:
        assert image.format == "PNG"
        assert image.size[0] > image.size[1] > 1_000
        image.verify()
