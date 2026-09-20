from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import trimesh


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("dual_lnbf_generate", HERE / "generate.py")
assert SPEC and SPEC.loader
generate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate)


@pytest.fixture(scope="module")
def holder() -> trimesh.Trimesh:
    return generate.build_holder()


def test_holder_is_one_watertight_printable_body(holder: trimesh.Trimesh) -> None:
    assert holder.is_watertight
    assert holder.is_volume
    assert holder.body_count == 1
    assert holder.volume > 0


def test_holder_has_flat_base_and_expected_envelope(holder: trimesh.Trimesh) -> None:
    lower, upper = holder.bounds
    assert lower[2] == pytest.approx(0.0, abs=1e-6)
    assert upper[2] < 105.0
    assert holder.extents[0] >= generate.BASE_ARM_LENGTH_MM
    assert holder.extents[1] >= generate.BASE_ARM_LENGTH_MM


def test_clip_contract() -> None:
    clip = generate.annular_clip(width_mm=10.0)
    assert clip.is_watertight
    assert clip.is_volume
    assert generate.BORE_DIAMETER_MM == pytest.approx(39.9)
    assert generate.AXIS_SPACING_MM == pytest.approx(80.0)
    assert generate.OUTWARD_TILT_DEG == pytest.approx(10.0)
    assert generate.CLIP_SWEEP_DEG == pytest.approx(360.0)


def test_bridge_is_behind_both_circular_bores() -> None:
    bridge_front_y = generate.BRIDGE_REAR_Y_MM + generate.BRIDGE_DEPTH_MM / 2.0
    assert bridge_front_y < -generate.BORE_DIAMETER_MM / 2.0


def test_assumed_bodies_have_clearance() -> None:
    assert generate.body_clearance() > 5.0
