from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import trimesh

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("lt3d002", HERE / "generate.py")
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


def test_released_vertical_snap_fit_contract(holder: trimesh.Trimesh) -> None:
    assert holder.bounds[0, 2] == pytest.approx(0.0, abs=1e-6)
    assert generate.AXIS_SPACING_MM == pytest.approx(80.0)
    assert generate.OUTWARD_TILT_DEG == pytest.approx(0.0)
    assert generate.CLIP_SWEEP_DEG == pytest.approx(242.0)
    assert generate.body_clearance() > 25.0


def test_snap_coupon_is_watertight() -> None:
    coupon = generate.snap_clip(width_mm=10.0)
    assert coupon.is_watertight
    assert coupon.is_volume
