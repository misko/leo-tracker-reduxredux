from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_post_refill_edge_switching_figures.py"
    spec = importlib.util.spec_from_file_location("post_refill_edge_switching_figures_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _published_results() -> Path:
    return (
        Path(__file__).parents[2]
        / "reports"
        / "figures"
        / "2026_08_27_post_refill_edge_switching"
        / "edge-switching-results.json"
    )


def test_published_receipt_exposes_edge_specific_retention() -> None:
    tool = _tool()

    document = tool.load_results(_published_results())
    _capture_id, _case, fine = tool._fine_case(document)
    shortest = min(tool._schedule_rows(fine), key=lambda item: item["dwell_s"])

    assert shortest["retained_lower_fraction_of_baseline_median"] == pytest.approx(0.3876464324)
    assert shortest["retained_upper_fraction_of_baseline_median"] == pytest.approx(0.3826530612)
    assert shortest["timing"][
        "uncertainty_envelope_retained_upper_fraction_of_baseline_median"
    ] == pytest.approx(0.1760204082)


def test_all_four_publication_figures_render(tmp_path: Path) -> None:
    tool = _tool()
    document = tool.load_results(_published_results())

    paths = tool.render_all(document, tmp_path)

    assert set(paths) == {"approach", "data_retention", "closure", "sensitivity"}
    for path in paths.values():
        png = path.read_bytes()
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", png[16:24])
        assert width >= 2_000
        assert height >= 900
