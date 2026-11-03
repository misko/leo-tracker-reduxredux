"""The execution-shape experiment must preserve unrelated native and Python code."""

import ast
from pathlib import Path

import pytest
from build_native_tile_probe import transform

ROOT = Path(__file__).resolve().parents[2] / "src/leo/analysis/starlink"


def sources():
    return [(ROOT / n).read_text() for n in
            ("_native_acquisition.c", "_native_acquisition_grid.inc", "acquisition.py")]


@pytest.mark.parametrize("lanes", [4, 8])
def test_only_execution_shape_changes(lanes):
    c, grid, py = sources()
    new_c, new_grid, new_py = transform(c, grid, py, lanes)
    assert new_c.replace(f"cfo_count == {lanes}", "cfo_count == 12") == c
    original_nodes, changed_nodes = ast.parse(py).body, ast.parse(new_py).body
    for before, after in zip(original_nodes, changed_nodes, strict=True):
        if getattr(before, "name", None) != "_folded_anchor_score_grid_native":
            assert ast.dump(before) == ast.dump(after)
    marker = "if (kernel->cfo_count == "
    assert grid.split(marker)[0] == new_grid.split(marker)[0]
    assert grid.split("} else {", 1)[1] == new_grid.split("} else {", 1)[1]
    branch = new_grid.split("} else {", 1)[0]
    assert "correlation_real_2" not in branch
    assert f"index * {lanes}" in branch
    assert branch.count("_mm256_fmadd_pd") == lanes // 4
    assert branch.count("_mm256_fnmadd_pd") == lanes // 4


def test_unknown_layout_and_invalid_tile_rejected():
    c, grid, py = sources()
    for args in [(c, grid, py, 7), (c, "", py, 8), ("", grid, py, 8),
                 (c, grid, "", 8), (c, grid, py.replace("12 - len(tile)", "7"), 8)]:
        with pytest.raises(ValueError):
            transform(*args)
