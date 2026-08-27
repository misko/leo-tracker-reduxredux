from __future__ import annotations

import copy
import importlib.util
import struct
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _tool() -> ModuleType:
    path = (
        Path(__file__).parents[2]
        / "tools"
        / "report_native_sample_rate_production_retrospective.py"
    )
    spec = importlib.util.spec_from_file_location(
        "native_sample_rate_production_retrospective_tool", path
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
        / "2026_08_27_native_sample_rate_production_retrospective"
        / "deployment-retrospective-data.json"
    )


def test_published_data_closes_native_rate_and_artifact_invariants() -> None:
    tool = _tool()

    document = tool._load(_published_data())

    assert [rate["sample_rate_hz"] for rate in document["native_rates"]] == [
        2_500_000,
        3_000_000,
        5_000_000,
    ]
    assert all(
        rate["sample_rate_hz"] == rate["rf_bandwidth_hz"] for rate in document["native_rates"]
    )
    assert sum(item["count"] for item in document["artifact_inventory"]) == 59
    assert all(item["artifact_count"] == 59 for item in document["http_artifact_checks"])


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda document: document["native_rates"][1].__setitem__("rf_bandwidth_hz", 2_500_000),
            "RF bandwidth",
        ),
        (
            lambda document: document["http_artifact_checks"][0].__setitem__("artifact_count", 58),
            "59 PNGs",
        ),
    ),
)
def test_validation_rejects_a_broken_production_invariant(mutation, message: str) -> None:
    tool = _tool()
    document = copy.deepcopy(tool._load(_published_data()))
    mutation(document)

    with pytest.raises(ValueError, match=message):
        tool._validate(document)


def test_all_six_retrospective_figures_render(tmp_path: Path) -> None:
    tool = _tool()
    document = tool._load(_published_data())
    renderers = {
        "rf_geometry": tool.render_rf_geometry,
        "transport": tool.render_transport,
        "continuity": tool.render_continuity,
        "performance": tool.render_performance,
        "timeline": tool.render_timeline,
        "flow": tool.render_flow,
    }

    assert set(renderers) == set(tool.FIGURE_NAMES)
    for key, renderer in renderers.items():
        path = tmp_path / tool.FIGURE_NAMES[key]
        renderer(path, document)
        png = path.read_bytes()
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", png[16:24])
        assert width >= 2_000
        assert height >= 900
