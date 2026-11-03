"""Geometry and surrogate assembly tests. No physical fit or load certification."""
import importlib.util
import hashlib
from pathlib import Path

import cadquery as cq
import numpy as np
import pytest
import trimesh

HERE = Path(__file__).resolve().parent


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


g = module(HERE / "generate.py", "angled_mount")
original = module(HERE.parent / "LT3D-002-dual-lnbf-snap-stand/generate.py", "original_snap")


@pytest.fixture(scope="module", params=[30, 40])
def design(request):
    return request.param, g.holder(request.param)


def test_snap_surface_vertices_are_preserved():
    before = sorted(map(tuple, np.round(original.snap_clip().vertices, 8)))
    after = sorted(tuple(round(c, 8) for c in v.toTuple()) for v in g.snap_clip().Vertices())
    assert before == after
    assert g.snap_clip().Volume() == pytest.approx(original.snap_clip().volume, abs=1e-6)
    for key in ("BORE_DIAMETER_MM", "WALL_MM", "CLIP_WIDTH_MM", "CLIP_SWEEP_DEG", "SEGMENTS"):
        assert getattr(g, key) == getattr(original, key)


def test_single_solid_flat_base(design):
    angle, h = design
    assert h.isValid() and len(h.Solids()) == 1
    assert h.BoundingBox().zmin == pytest.approx(0, abs=1e-7)
    assert h.BoundingBox().xlen < 180
    assert h.BoundingBox().ylen <= 101
    assert h.Volume() > 0


def test_actual_axes_and_shared_baseline(design):
    angle, _ = design
    positions, directions = [], []
    for side in (-1, 1):
        a = g.place(cq.Vertex.makeVertex(0, 0, 0), side, angle).toTuple()
        b = g.place(cq.Vertex.makeVertex(0, 0, 1), side, angle).toTuple()
        positions.append(a)
        directions.append(np.array(b)-a)
    assert np.linalg.norm(np.array(positions[1])-positions[0]) == pytest.approx(120)
    assert np.rad2deg(np.arccos(np.dot(*directions))) == pytest.approx(angle)


@pytest.mark.parametrize("name", list(g.ENVELOPES))
def test_clearance_excludes_only_intended_neck_interference(design, name):
    angle, h = design
    check = g.verify_assembly(h, angle, name)
    assert check["pair_gap_mm"] >= 5
    assert check["pair_intersection_mm3"] < 1e-6
    for rx in check["receivers"]:
        assert rx["minimum_z_mm"] >= 10
        assert rx["non_neck_intersection_mm3"] < 1e-6
        assert rx["non_neck_mount_gap_mm"] >= 2
        assert rx["neck_interference_mm3"] > 0  # 40 mm neck in proven 39.9 mm bore


def test_exported_stl_and_step_match_design(design):
    angle, h = design
    part = "LT3D-003A" if angle == 30 else "LT3D-003B"
    stem = HERE / f"{part}-{angle}deg-snap-stand"
    mesh = trimesh.load_mesh(stem.with_suffix(".stl"))
    assert mesh.is_watertight and mesh.is_volume and mesh.body_count == 1
    assert mesh.volume == pytest.approx(h.Volume(), rel=0.001)
    shape = cq.importers.importStep(str(stem.with_suffix(".step"))).val()
    assert shape.isValid() and len(shape.Solids()) == 1
    assert shape.Volume() == pytest.approx(h.Volume(), rel=1e-7)


def test_downloads_are_preserved_step_references_not_qualified_fit_models():
    expected = {
        "norsat-2000-f.step": "e80b352d366a45754824d1553540eefe5df2ec8ee7dc4ef6730378f96ec57d2c",
        "norsat-2000-n.step": "f1ada53c3a3100717df84ada5075538dacb6ef991a5551d2d72617f97d46aaa8",
    }
    assert {p.name for p in (HERE / "references").glob("*.step")} == set(expected)
    for p in (HERE / "references").glob("*.step"):
        assert hashlib.sha256(p.read_bytes()).hexdigest() == expected[p.name]
        assert p.read_text().startswith("ISO-10303-21;")
        shape = cq.importers.importStep(str(p)).val()
        assert len(shape.Solids()) > 0 and shape.Volume() > 0
        # These source files contain invalid topology in OCCT. Preserve the
        # originals and explicitly reject, rather than silently healing them.
        assert not shape.isValid()


def test_wide_body_entry_path_stays_clear_of_mount(design):
    angle, mount = design
    for side in (-1, 1):
        for name, shape in g.reference_parts("wide-60").items():
            if name == "neck":
                continue  # intentional elastic snap contact, not a rigid motion
            positioned = g.place(shape, side, angle)
            for offset in (0, 10, 30, 80):
                assert g.volume_common(positioned.translate((0, offset, 0)), mount) < 1e-6
