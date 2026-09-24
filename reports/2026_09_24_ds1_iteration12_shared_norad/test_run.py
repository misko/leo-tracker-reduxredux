from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def module():
    path = Path(__file__).parent / "run.py"
    spec = importlib.util.spec_from_file_location("ds1i12test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_lattice_is_symmetric_and_includes_seed():
    m = module()
    points = m.lattice({"latitude_deg": 37.0, "longitude_deg": -122.0})
    assert len(points) == 9
    offsets = {
        (point["east_km_from_iteration10"], point["north_km_from_iteration10"])
        for point in points
    }
    assert offsets == {
        (east, north)
        for east in (-m.SPACING_KM, 0.0, m.SPACING_KM)
        for north in (-m.SPACING_KM, 0.0, m.SPACING_KM)
    }


def test_source_groups_exposes_cross_group_overlap_without_session_prefix():
    m = module()

    class Data:
        def __init__(self, values):
            self.source = __import__("numpy").asarray(values, dtype=object)

    groups = m.source_groups(
        {"20260921_00": Data(["100", "200"]), "20260921_16": Data(["200", "300"])}
    )
    assert groups == {
        "100": ["20260921_00"],
        "200": ["20260921_00", "20260921_16"],
        "300": ["20260921_16"],
    }


def test_selection_prefers_loss_then_seed_distance():
    m = module()
    common = {"latitude_deg": 1.0, "longitude_deg": 2.0}
    first = {
        **common,
        "east_km_from_iteration10": 0.01,
        "north_km_from_iteration10": 0.0,
        "fit": {"balanced_exact_capped_loss": 0.1},
    }
    second = {
        **common,
        "east_km_from_iteration10": 0.0,
        "north_km_from_iteration10": 0.0,
        "fit": {"balanced_exact_capped_loss": 0.1},
    }
    assert min([first, second], key=m.selection_key) is second
