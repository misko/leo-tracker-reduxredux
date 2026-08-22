from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest


def _tool():
    path = Path(__file__).parents[2] / "tools" / "report_frame_local_phase_qualification.py"
    spec = importlib.util.spec_from_file_location("report_frame_local_phase_qualification", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_frozen_boundary_models_are_degree_one() -> None:
    module = _tool()
    for boundary in module.BOUNDARIES:
        grid = np.asarray((boundary.time_s - 0.1, boundary.time_s, boundary.time_s + 0.1))
        for segment in (boundary.pre, boundary.post):
            frequencies = segment.frequency_hz(grid)
            assert np.diff(frequencies)[0] == pytest.approx(np.diff(frequencies)[1])


def test_candidate_selection_uses_one_candidate_per_independent_probe() -> None:
    module = _tool()
    boundary = module.BOUNDARIES[0]
    expected = float(boundary.pre.frequency_hz(26.0))
    candidates = (
        module.Candidate(100, 26.0, 0, 2, expected + 100, 0.4, 0.1, 0.3),
        module.Candidate(100, 26.0, 1, 3, expected + 20, 0.3, 0.1, 0.2),
        module.Candidate(200, 26.1, 0, 2, expected + 50_000, 0.4, 0.1, 0.3),
    )

    selected = module._select_line_candidates(boundary, candidates)

    assert len(selected) == 1
    assert selected[0].rank == 1


def test_phase_increment_is_computed_only_within_one_probe() -> None:
    module = _tool()

    def record(probe: int, frame: int, phase: float):
        return module.FrameRecord(
            "b1",
            "pre",
            probe,
            float(probe),
            frame,
            float(probe) + frame / 750,
            phase,
            1.0,
            0.0,
            1.0,
            0.0,
            0.25,
            0.0,
            0.0,
            np.ones(4, dtype=np.complex128) / 2,
        )

    times, increments = module._phase_increments(
        (record(0, 0, 0.1), record(0, 1, 0.2), record(1, 0, -0.4), record(1, 1, 0.4))
    )

    assert len(times) == 2
    assert np.allclose(increments, (0.1, -0.2))


def test_frame_artifact_is_byte_reproducible(tmp_path: Path) -> None:
    module = _tool()
    first = tmp_path / "first.jsonl.gz"
    second = tmp_path / "second.jsonl.gz"

    module._write_frame_artifact({}, 1_000_000, first)
    module._write_frame_artifact({}, 1_000_000, second)

    assert first.read_bytes() == second.read_bytes()


def test_standalone_report_defines_boundaries_and_method(tmp_path: Path) -> None:
    module = _tool()
    root = Path(__file__).parents[2]
    metrics = json.loads(
        (
            root
            / "reports/figures/2026_08_22_frame_local_phase_qualification"
            / "frame-local-phase-metrics.json"
        ).read_text(encoding="utf-8")
    )
    report = tmp_path / "report.md"

    module._report(metrics, report)
    rendered = report.read_text(encoding="utf-8")

    assert "## 1. Why this question matters" in rendered
    assert "## 3. Terminology" in rendered
    assert "### 5.2 Step-by-step estimator" in rendered
    assert "Boundary 1 (B1)" in rendered
    assert "P1" in rendered and "P2" in rendered
    assert "not satellite names" in rendered


def test_method_illustration_renders(tmp_path: Path) -> None:
    module = _tool()
    root = Path(__file__).parents[2]
    metrics = json.loads(
        (
            root
            / "reports/figures/2026_08_22_frame_local_phase_qualification"
            / "frame-local-phase-metrics.json"
        ).read_text(encoding="utf-8")
    )
    figure = tmp_path / "method.png"

    module._plot_question_and_method(metrics, figure)

    assert figure.stat().st_size > 10_000
