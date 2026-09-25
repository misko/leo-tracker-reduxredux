"""Generate a free-standing, vertical, snap-in dual-LNBF holder."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import trimesh


HERE = Path(__file__).resolve().parent

NECK_DIAMETER_MM = 40.0
BORE_DIAMETER_MM = 39.9
WALL_MM = 4.5
CLIP_WIDTH_MM = 24.0
CLIP_SWEEP_DEG = 242.0
AXIS_SPACING_MM = 80.0
OUTWARD_TILT_DEG = 0.0

AXIS_HEIGHT_MM = 76.0
BRIDGE_DEPTH_MM = 10.0
BRIDGE_HEIGHT_MM = 16.0
# The bridge overlaps only the rear outer clip walls, not either bore.
BRIDGE_REAR_Y_MM = -26.5
STEM_WIDTH_MM = 18.0
STEM_DEPTH_MM = 18.0
BASE_HEIGHT_MM = 10.0
BASE_ARM_LENGTH_MM = 82.0
BASE_ARM_WIDTH_MM = 18.0
SEGMENTS = 160


def _box(extents: tuple[float, float, float], center: tuple[float, float, float]) -> trimesh.Trimesh:
    transform = np.eye(4)
    transform[:3, 3] = center
    return trimesh.creation.box(extents=extents, transform=transform)


def snap_clip(width_mm: float = CLIP_WIDTH_MM) -> trimesh.Trimesh:
    """Return a watertight C-clip, local +Z axial and opening toward +Y."""
    inner = BORE_DIAMETER_MM / 2.0
    outer = inner + WALL_MM
    missing = 360.0 - CLIP_SWEEP_DEG
    start = math.radians(90.0 + missing / 2.0)
    stop = start + math.radians(CLIP_SWEEP_DEG)
    angles = np.linspace(start, stop, SEGMENTS)
    z0, z1 = -width_mm / 2.0, width_mm / 2.0
    vertices: list[list[float]] = []
    for angle in angles:
        c, s = math.cos(angle), math.sin(angle)
        vertices.extend([
            [inner * c, inner * s, z0], [outer * c, outer * s, z0],
            [inner * c, inner * s, z1], [outer * c, outer * s, z1],
        ])
    faces: list[list[int]] = []
    for index in range(len(angles) - 1):
        a, b = 4 * index, 4 * (index + 1)
        faces.extend([
            [a, b, b + 2], [a, b + 2, a + 2],
            [a + 1, a + 3, b + 3], [a + 1, b + 3, b + 1],
            [a, a + 1, b + 1], [a, b + 1, b],
            [a + 2, b + 2, b + 3], [a + 2, b + 3, a + 3],
        ])
    last = 4 * (len(angles) - 1)
    faces.extend([
        [0, 2, 3], [0, 3, 1],
        [last, last + 1, last + 3], [last, last + 3, last + 2],
    ])
    mesh = trimesh.Trimesh(vertices=np.asarray(vertices), faces=np.asarray(faces), process=True)
    trimesh.repair.fix_normals(mesh)
    return mesh


def placed_clip(side: int) -> trimesh.Trimesh:
    clip = snap_clip()
    rotation = trimesh.transformations.rotation_matrix(
        math.radians(side * OUTWARD_TILT_DEG), [0.0, 1.0, 0.0]
    )
    clip.apply_transform(rotation)
    clip.apply_translation([side * AXIS_SPACING_MM / 2.0, 0.0, AXIS_HEIGHT_MM])
    return clip


def build_holder() -> trimesh.Trimesh:
    clip_outer = BORE_DIAMETER_MM / 2.0 + WALL_MM
    bridge = _box((AXIS_SPACING_MM + 2 * clip_outer, BRIDGE_DEPTH_MM, BRIDGE_HEIGHT_MM),
                  (0.0, BRIDGE_REAR_Y_MM, AXIS_HEIGHT_MM))
    stem_top = AXIS_HEIGHT_MM - BRIDGE_HEIGHT_MM / 2.0 + 1.0
    stem_bottom = BASE_HEIGHT_MM - 1.0
    stem = _box((STEM_WIDTH_MM, STEM_DEPTH_MM, stem_top - stem_bottom),
                (0.0, BRIDGE_REAR_Y_MM, (stem_top + stem_bottom) / 2.0))
    foot_x = _box((BASE_ARM_LENGTH_MM, BASE_ARM_WIDTH_MM, BASE_HEIGHT_MM),
                  (0.0, BRIDGE_REAR_Y_MM, BASE_HEIGHT_MM / 2.0))
    foot_y = _box((BASE_ARM_WIDTH_MM, BASE_ARM_LENGTH_MM, BASE_HEIGHT_MM),
                  (0.0, BRIDGE_REAR_Y_MM, BASE_HEIGHT_MM / 2.0))
    holder = trimesh.boolean.union([placed_clip(-1), placed_clip(1), bridge, stem, foot_x, foot_y],
                                   engine="manifold")
    if isinstance(holder, list):
        holder = trimesh.util.concatenate(holder)
    holder.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(holder)
    return holder


def body_clearance(body_diameter_mm: float = 50.0, below_clip_mm: float = 65.0) -> float:
    separation = AXIS_SPACING_MM - 2 * below_clip_mm * math.sin(math.radians(OUTWARD_TILT_DEG))
    return separation - body_diameter_mm


def main() -> None:
    holder = build_holder()
    coupon = snap_clip(width_mm=10.0)
    holder.export(HERE / "LT3D-002A-dual-lnbf-snap-stand.stl")
    coupon.export(HERE / "LT3D-002B-lnbf-snap-fit-test.stl")
    print(f"neck axes: {AXIS_SPACING_MM:.1f} mm apart, vertical")
    print(f"snap-entry mouth: {2 * (BORE_DIAMETER_MM / 2) * math.sin(math.radians((360 - CLIP_SWEEP_DEG) / 2)):.2f} mm")
    print(f"nominal Ø50 body clearance: {body_clearance():+.1f} mm")


if __name__ == "__main__":
    main()
