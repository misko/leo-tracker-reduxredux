from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_five_dwell_pilot_filter_prototypes.py"
    spec = importlib.util.spec_from_file_location("five_dwell_pilot_filter_prototypes_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_npz(path: Path, *, include_odd_window: bool = True) -> None:
    frame_count = 75
    window_indices = (0, 1) if include_odd_window else (0,)
    arrays: dict[str, list[np.ndarray]] = {
        key: []
        for key in (
            "window_index",
            "window_center_time_s",
            "window_raw_disjoint",
            "frame_index",
            "absolute_time_s",
            "absolute_cfo_measurement_hz",
            "measurement_sigma_hz",
            "measurement_supported",
            "exact_coherence",
            "control_coherence",
            "frequency_innovation_hz",
            "tracked_absolute_cfo_hz",
            "tracked_rate_hz_s",
            "tracked_rate_sigma_hz_s",
            "phase_innovation_rad",
            "phase_update",
            "reacquired",
        )
    }
    for index in window_indices:
        start_s = 0.2 * index
        time_s = start_s + np.arange(frame_count) / 750.0
        cfo_hz = 20_000.0 - 3_000.0 * time_s + 7.0 * np.sin(np.arange(frame_count) * 0.63)
        rows = {
            "window_index": np.full(frame_count, index, dtype=int),
            "window_center_time_s": np.full(frame_count, start_s + 0.05),
            "window_raw_disjoint": np.full(frame_count, index % 2 == 0),
            "frame_index": np.arange(frame_count, dtype=int),
            "absolute_time_s": time_s,
            "absolute_cfo_measurement_hz": cfo_hz,
            "measurement_sigma_hz": np.full(frame_count, 20.0),
            "measurement_supported": np.ones(frame_count, dtype=bool),
            "exact_coherence": np.full(frame_count, 0.50),
            "control_coherence": np.full(frame_count, 0.05),
            "frequency_innovation_hz": np.linspace(80.0, 120.0, frame_count),
            "tracked_absolute_cfo_hz": cfo_hz - 100.0,
            "tracked_rate_hz_s": np.full(frame_count, -3_000.0),
            "tracked_rate_sigma_hz_s": np.full(frame_count, 100.0),
            "phase_innovation_rad": np.zeros(frame_count),
            "phase_update": np.ones(frame_count, dtype=bool),
            "reacquired": np.zeros(frame_count, dtype=bool),
        }
        for key, values in rows.items():
            arrays[key].append(values)
    np.savez_compressed(path, **{key: np.concatenate(values) for key, values in arrays.items()})


def _summary(
    tool: ModuleType,
    *,
    session_id: str,
    label: str,
    npz_path: Path,
) -> dict[str, object]:
    pnt_source = npz_path.parent / "synthetic-pnt.py"
    pnt_source.write_text("# frozen synthetic PNT implementation\n", encoding="utf-8")
    seed_source = npz_path.parent / "synthetic-seeds.json"
    seed_source.write_text(json.dumps({"selection": "synthetic"}), encoding="utf-8")
    exact_windows = [
        {"window_index": index, "center_time_s": index * 0.1 + 0.05, "qualified": index == 0}
        for index in range(3)
    ]
    rolled_windows = [
        {"window_index": index, "center_time_s": index * 0.1 + 0.05, "qualified": False}
        for index in range(3)
    ]
    return {
        "schema": tool.SOURCE_SCHEMA,
        "session_id": session_id,
        "dwell_label": label,
        "stream_id": "stream-1",
        "receiver_id": 1,
        "edge": "upper",
        "capture_release_sha": "release-synthetic",
        "selection": "strongest frozen GLRT margin in each 100 ms bin",
        "window_count": 3,
        "raw_disjoint_window_count": 2,
        "frame_count": 150,
        "npz_relative_path": npz_path.name,
        "npz_sha256": _sha256(npz_path),
        "seed_relative_path": seed_source.name,
        "seed_sha256": _sha256(seed_source),
        "pnt_source_path": str(pnt_source),
        "pnt_source_sha256": _sha256(pnt_source),
        "exact": {"qualified_count": 1, "supported_frames": 150},
        "rolled": {"qualified_count": 0, "supported_frames": 0},
        "exact_windows": exact_windows,
        "rolled_windows": rolled_windows,
    }


def _five_sources(tool: ModuleType, root: Path) -> tuple[Any, ...]:
    pnt_source = root / "cohort-pnt.py"
    pnt_source.write_text("# frozen cohort PNT\n", encoding="utf-8")
    labels = ("D1", "D2", "D4", "D5", "D6")
    summaries = []
    for index, label in enumerate(labels):
        npz = root / f"{label.lower()}-filter-benchmark.npz"
        np.savez(npz, marker=np.asarray((index,)))
        seed = root / f"{label.lower()}-seeds.json"
        seed.write_text(json.dumps({"label": label}), encoding="utf-8")
        summary = {
            "schema": tool.SOURCE_SCHEMA,
            "session_id": f"session-{index}",
            "label": label,
            "pipeline_release_id": "one-release",
            "npz_relative_path": npz.name,
            "npz_sha256": _sha256(npz),
            "seed_relative_path": seed.name,
            "seed_sha256": _sha256(seed),
            "pnt_source_path": str(pnt_source),
            "pnt_source_sha256": _sha256(pnt_source),
        }
        summary_path = root / f"{label.lower()}-filter-benchmark-summary.json"
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        summaries.append(summary_path)
    return tool.discover_sources(
        root,
        tuple(summaries),
        enforce_primary=False,
    )


def _parity_document(tool: ModuleType, sources: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "schema": tool.PARITY_SCHEMA,
        "executed_pnt_source_sha256": sources[0].pnt_source_sha256,
        "all_seed_json_identical": True,
        "all_npz_identical": True,
        "rows": [
            {
                "label": source.label,
                "seed_sha256": source.summary["seed_sha256"],
                "npz_sha256": source.summary["npz_sha256"],
                "seed_json_identical": True,
                "npz_identical": True,
            }
            for source in sources
        ],
    }


def test_discovery_requires_five_unique_same_release_sources(tmp_path: Path) -> None:
    tool = _tool()
    pnt_source = tmp_path / "pnt.py"
    pnt_source.write_text("# one frozen PNT source\n", encoding="utf-8")
    for index in range(5):
        npz = tmp_path / f"d{index}-filter-benchmark.npz"
        np.savez(npz, marker=np.asarray((index,)))
        seed = tmp_path / f"d{index}-seeds.json"
        seed.write_text(json.dumps({"dwell": index}), encoding="utf-8")
        summary = {
            "schema": tool.SOURCE_SCHEMA,
            "session_id": f"session-{index}",
            "dwell_label": f"D{index}",
            "capture_release_sha": "one-release",
            "npz_relative_path": npz.name,
            "npz_sha256": _sha256(npz),
            "seed_relative_path": seed.name,
            "seed_sha256": _sha256(seed),
            "pnt_source_path": str(pnt_source),
            "pnt_source_sha256": _sha256(pnt_source),
        }
        (tmp_path / f"d{index}-filter-benchmark-summary.json").write_text(
            json.dumps(summary), encoding="utf-8"
        )

    sources = tool.discover_sources(tmp_path, enforce_primary=False)

    assert len(sources) == 5
    assert {source.release_sha for source in sources} == {"one-release"}
    assert all(source.npz_path.is_absolute() for source in sources)

    damaged = Path(sources[0].npz_path)
    original_npz = damaged.read_bytes()
    damaged.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        tool.discover_sources(tmp_path, enforce_primary=False)
    damaged.write_bytes(original_npz)

    damaged_seed = sources[0].source_paths[0]
    original_seed = damaged_seed.read_text(encoding="utf-8")
    damaged_seed.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="seed SHA-256 mismatch"):
        tool.discover_sources(tmp_path, enforce_primary=False)
    damaged_seed.write_text(original_seed, encoding="utf-8")

    alternate_pnt = tmp_path / "alternate-pnt.py"
    alternate_pnt.write_text("# a different PNT source\n", encoding="utf-8")
    first_summary = tmp_path / "d0-filter-benchmark-summary.json"
    document = json.loads(first_summary.read_text(encoding="utf-8"))
    document["pnt_source_path"] = str(alternate_pnt)
    document["pnt_source_sha256"] = _sha256(alternate_pnt)
    first_summary.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="different PNT implementations"):
        tool.discover_sources(tmp_path, enforce_primary=False)


def test_parity_attestation_is_required_and_fails_closed_on_mismatch(
    tmp_path: Path,
) -> None:
    tool = _tool()
    sources = _five_sources(tool, tmp_path)
    parity_path = tmp_path / "source-replay-parity-attestation.json"

    with pytest.raises(ValueError, match="attestation is missing"):
        tool.validate_parity_attestation(parity_path, sources)

    valid = _parity_document(tool, sources)
    parity_path.write_text(json.dumps(valid), encoding="utf-8")
    attestation = tool.validate_parity_attestation(parity_path, sources)
    assert attestation.sha256 == _sha256(parity_path)
    assert attestation.document == valid

    mutations = (
        (
            "false global parity",
            lambda row: row.update({"all_npz_identical": False}),
            "does not attest all NPZ",
        ),
        (
            "label mismatch",
            lambda row: row["rows"][0].update({"label": "DX"}),
            "labels do not exactly match",
        ),
        (
            "seed digest mismatch",
            lambda row: row["rows"][0].update({"seed_sha256": "0" * 64}),
            "parity seed digest disagrees",
        ),
        (
            "NPZ digest mismatch",
            lambda row: row["rows"][0].update({"npz_sha256": "f" * 64}),
            "parity NPZ digest disagrees",
        ),
        (
            "PNT digest mismatch",
            lambda row: row.update({"executed_pnt_source_sha256": "1" * 64}),
            "executed PNT digest disagrees",
        ),
    )
    for _, mutate, message in mutations:
        damaged = copy.deepcopy(valid)
        mutate(damaged)
        parity_path.write_text(json.dumps(damaged), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            tool.validate_parity_attestation(parity_path, sources)

    parity_path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="not readable JSON"):
        tool.validate_parity_attestation(parity_path, sources)


def test_recording_block_equal_rms_does_not_flatten_dense_seconds() -> None:
    tool = _tool()
    keys = ((0, 0), (0, 1), (0, 2), (0, 3))
    time_s = dict(zip(keys, (0.1, 0.2, 0.3, 1.1), strict=True))
    residual = dict(zip(keys, (1.0, 1.0, 1.0, 9.0), strict=True))

    result = tool.recording_block_equal_statistics(residual, time_s)

    assert result["frame_count"] == 4
    assert result["recording_anchored_one_second_block_count"] == 2
    assert result["recording_second_indices"] == [0, 1]
    assert result["block_equal_rms_hz"] == pytest.approx(np.sqrt((1.0 + 81.0) / 2.0))
    assert result["block_equal_rms_hz"] != pytest.approx(np.sqrt((1.0 + 1.0 + 1.0 + 81.0) / 4.0))


def test_pairwise_mask_ignores_candidate_only_frames() -> None:
    tool = _tool()
    d3 = tool._d3_tool()
    common = ((0, 0), (0, 1), (1, 0), (1, 1))
    time_s = dict(zip(common, (0.2, 0.3, 1.2, 1.3), strict=True))
    candidate = d3.PredictionSeries(
        "candidate",
        {**{key: 2.0 for key in common}, (99, 99): 100_000.0},
        {},
        {},
    )
    baseline = d3.PredictionSeries("baseline", {key: 4.0 for key in common}, {}, {})

    result = tool.pairwise_block_comparison(candidate, baseline, time_s)

    assert result["common_frame_count"] == 4
    assert result["recording_anchored_one_second_block_count"] == 2
    assert result["candidate_to_baseline_rms_ratio"] == pytest.approx(0.5)
    assert result["fractional_rms_improvement"] == pytest.approx(0.5)


def test_exact_two_sided_sign_test_uses_only_dwell_outcomes() -> None:
    tool = _tool()

    all_wins = tool.exact_two_sided_sign_test([0.8] * 5)
    mixed = tool.exact_two_sided_sign_test([0.8, 0.9, 1.0, 1.1, 1.2])

    assert all_wins["candidate_better_fraction_of_non_ties"] == 1.0
    assert all_wins["exact_two_sided_sign_probability"] == pytest.approx(0.0625)
    assert mixed["non_tied_dwell_count"] == 4
    assert mixed["tied_dwell_count"] == 1
    assert mixed["exact_two_sided_sign_probability"] == pytest.approx(1.0)


def test_synthetic_evaluation_preserves_no_row_bins_and_renders_static_outputs(
    tmp_path: Path,
) -> None:
    tool = _tool()
    npz = tmp_path / "synthetic-filter-benchmark.npz"
    _write_npz(npz)
    summary = _summary(
        tool,
        session_id="session-0",
        label="D1",
        npz_path=npz,
    )
    summary_path = tmp_path / "synthetic-filter-benchmark-summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    source = tool._load_source(summary_path)

    evaluated = tool.evaluate_dwell(source)

    assert evaluated.evidence["corpus"]["planned_even_raw_disjoint_window_count"] == 2
    assert evaluated.evidence["corpus"]["emitted_even_raw_disjoint_window_count"] == 1
    assert evaluated.evidence["corpus"]["even_raw_disjoint_bins_without_frame_rows"] == 1
    assert evaluated.evidence["all_causal_common_mask"]["common_frame_count"] > 0
    assert evaluated.evidence["phase_lock"]["rolled_qin_qualified_windows"] == 0

    sources = []
    evaluations = []
    labels = ("D1", "D2", "D4", "D5", "D6")
    for index, label in enumerate(labels):
        sources.append(
            replace(
                source,
                label=label,
                session_id=f"session-{index + 1}",
            )
        )
        cloned_evidence = copy.deepcopy(evaluated.evidence)
        cloned_evidence["label"] = label
        cloned_evidence["session_id"] = f"session-{index + 1}"
        if label == "D4":
            reason = "synthetic all-causal completeness failure"
            cloned_evidence["estimability"] = {
                "status": "not_estimable",
                "criterion": "synthetic",
                "reason": reason,
            }
            cloned_evidence["all_causal_common_mask"] = {
                "status": "not_estimable",
                "models": list(tool.CAUSAL_MODELS),
                "common_frame_count": 0,
                "recording_anchored_one_second_block_count": 0,
                "model_statistics": {},
                "reason": reason,
            }
            for comparison in cloned_evidence["pairwise_common_masks"].values():
                comparison.clear()
                comparison.update(
                    {
                        "status": "not_estimable",
                        "candidate": "synthetic",
                        "baseline": "synthetic",
                        "reason": reason,
                    }
                )
        evaluations.append(
            tool.DwellEvaluation(
                evidence=cloned_evidence,
                plotting=evaluated.plotting,
            )
        )
    parity_path = tmp_path / "source-replay-parity-attestation.json"
    parity_path.write_text(json.dumps(_parity_document(tool, tuple(sources))), encoding="utf-8")
    parity = tool.validate_parity_attestation(parity_path, tuple(sources))
    evidence = tool.build_evidence(tuple(sources), tuple(evaluations), parity)
    assert evidence["source_replay_parity_attestation"]["sha256"] == _sha256(parity_path)
    assert evidence["source_replay_parity_attestation"]["validated_document"] == (parity.document)
    assert evidence["aggregate_equal_dwell"]["primary_five_dwell"]["status"] == ("not_estimable")
    assert evidence["aggregate_equal_dwell"]["complete_case_sensitivity"][
        "estimable_dwell_labels"
    ] == ["D1", "D2", "D5", "D6"]
    assert (
        evidence["aggregate_equal_dwell"]["pairwise_common_masks"][
            "robust_jump_filter_vs_current_v2"
        ]["frame_level_resampling_performed"]
        is False
    )

    tool._style()
    figures = {
        "common_rms": tmp_path / "common.png",
        "effects": tmp_path / "effects.png",
        "calibration": tmp_path / "calibration.png",
        "phase": tmp_path / "phase.png",
        "timelines": tmp_path / "timelines.png",
    }
    tool._plot_common_mask_rms(figures["common_rms"], evidence)
    tool._plot_effects(figures["effects"], evidence)
    tool._plot_calibration_utilization(figures["calibration"], evidence)
    tool._plot_phase_control(figures["phase"], evidence)
    tool._plot_timelines(figures["timelines"], tuple(evaluations))
    for figure in figures.values():
        assert figure.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    report = tmp_path / "report.md"
    tool._write_report(
        report,
        evidence,
        {name: path.name for name, path in figures.items()},
    )
    text = report.read_text(encoding="utf-8")
    assert "does not flatten frames into one pseudo-sample" in text
    assert "not continuous 60 s tracks" in text
    assert "No TLE, orbit, satellite visibility, or satellite identity" in text
    assert "Planned even bins that emitted no frame rows remain explicit" in text
    assert "predeclared primary five-dwell effect is unavailable" in text
    assert "complete-case sensitivity only" in text
