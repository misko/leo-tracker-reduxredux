from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _tool():
    path = Path(__file__).parents[2] / "tools" / "explore_all_pilot_method_tracks.py"
    spec = importlib.util.spec_from_file_location("explore_all_pilot_method_tracks_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_each_family_has_an_explicit_score_scale_and_cfo_source() -> None:
    tool = _tool()

    methods = {method.key: method for method in tool.METHODS}

    assert tuple(methods) == (
        "anchor8",
        "differential16",
        "differential32",
        "glrt32",
        "glrt64",
        "edge_tracker",
        "symbolwise",
        "qam_accuracy",
    )
    assert methods["anchor8"].residual_field is None
    assert methods["differential32"].residual_field == "differential32_residual_cfo_hz"
    assert methods["glrt64"].residual_field == "glrt64_residual_cfo_hz"
    assert methods["edge_tracker"].minimum_selection == 0.05
    assert methods["qam_accuracy"].minimum_selection == 0.60
    assert methods["qam_accuracy"].selection_label == "hard-symbol accuracy"


def test_output_name_is_stable_and_method_specific() -> None:
    tool = _tool()
    output = tool._output_path(
        Path("artifacts"),
        Path("example-stream-0-rx0-pilot-methods.csv"),
        tool.METHODS[0],
    )

    assert output == Path("artifacts/example-stream-0-rx0-anchor8-tracks.png")
