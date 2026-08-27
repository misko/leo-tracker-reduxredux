from __future__ import annotations

import copy
import importlib.util
import struct
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_170330_capture_quality_figures.py"
    spec = importlib.util.spec_from_file_location(
        "report_170330_capture_quality_figures_tool", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _published_data() -> Path:
    return (
        Path(__file__).parents[2]
        / "reports"
        / "figures"
        / "2026_08_27_170330_capture_quality"
        / "capture-quality-results.json"
    )


def test_published_data_closes_capture_quality_and_claim_invariants() -> None:
    tool = _tool()
    document = tool._load(_published_data())

    prior = document["captures"]["prior"]
    new = document["captures"]["new"]
    assert prior["sample_rate_hz"] == new["sample_rate_hz"] == 5_000_000
    assert prior["gap_count"] == 61
    assert new["gap_count"] == 0
    assert prior["segment_count"] == prior["gap_count"] + 1
    assert new["segment_count"] == new["gap_count"] + 1
    assert new["glrt"]["passing_windows"] == 5_987
    assert new["glrt"]["valid_windows"] == 5_999
    path_inventory = document["new_capture_path_inventory"]["paths"]
    assert len(path_inventory) == 4
    assert {path["receiver_id"] for path in path_inventory} == {0, 1}
    assert all(path["known_pilot_rms_evm"] > 0 for path in path_inventory)
    assert document["timing_evaluation"]["method"]["windows_overlap_fraction"] == 0.5
    assert document["timing_evaluation"]["method"]["residual_evaluation"] == "in-sample"
    phase = document["phase_tracking_comparison"]
    assert phase["new_lower_rx1"]["phase_qualified_segment_count"] == 0
    assert phase["new_lower_rx0"]["phase_qualified_segment_count"] == 10
    assert phase["absolute_carrier_phase_resolved"] is False
    assert document["claim_boundary"]["bandwidth_causality_claimed"] is False
    assert document["claim_boundary"]["absolute_toa_accuracy_measured"] is False
    assert document["claim_boundary"]["blind_end_to_end"] is False


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda document: document["claim_boundary"].__setitem__(
                "bandwidth_causality_claimed", True
            ),
            "bandwidth causality",
        ),
        (
            lambda document: document["captures"]["new"]["glrt"].__setitem__(
                "passing_windows", 6_000
            ),
            "exceeds valid",
        ),
        (
            lambda document: document["captures"]["prior"].__setitem__("segment_count", 61),
            "segment accounting",
        ),
        (
            lambda document: document["phase_tracking_comparison"].__setitem__(
                "absolute_carrier_phase_resolved", True
            ),
            "unresolved absolute-phase",
        ),
    ),
)
def test_validation_rejects_false_or_broken_claims(mutation, message: str) -> None:
    tool = _tool()
    document = copy.deepcopy(tool._load(_published_data()))
    mutation(document)

    with pytest.raises(ValueError, match=message):
        tool._validate(document)


def test_all_four_capture_quality_figures_render(tmp_path: Path) -> None:
    tool = _tool()
    document = tool._load(_published_data())
    renderers = {
        "integrity": tool.render_integrity,
        "glrt": tool.render_glrt,
        "timing": tool.render_timing,
        "claims": tool.render_claim_boundary,
    }

    assert set(renderers) == set(tool.FIGURE_NAMES)
    for key, renderer in renderers.items():
        path = tmp_path / tool.FIGURE_NAMES[key]
        renderer(path, document)
        png = path.read_bytes()
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", png[16:24])
        assert width >= 2_000
        assert height >= 1_300
