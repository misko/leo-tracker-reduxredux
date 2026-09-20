"""Generate a compact, free-standing holder for two tilted Ø40 mm LNBFs.

The two neck axes are 80 mm apart and tilt 10 degrees away from one another.
The closed rings share a rear bridge. A central web and crossed bottom foot make
the holder free-standing while keeping its top-view footprint small.
"""
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
# A closed ring gives each LNBF a fully circular through-hole. The LNBF must be
# installed axially; this is intentionally not a snap-fit C-clip.
CLIP_SWEEP_DEG = 360.0
AXIS_SPACING_MM = 80.0
OUTWARD_TILT_DEG = 10.0

AXIS_HEIGHT_MM = 76.0
BRIDGE_DEPTH_MM = 10.0
BRIDGE_HEIGHT_MM = 16.0
# Its front is 1.55 mm behind the 19.95 mm bore radius. It overlaps the rear
# outer clip walls for strength but cannot cross either circular neck bore.
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


def annular_clip(width_mm: float = CLIP_WIDTH_MM) -> trimesh.Trimesh:
    """Return a watertight closed ring with a fully circular local +Z bore."""
    inner = BORE_DIAMETER_MM / 2.0
    outer = inner + WALL_MM
    angles = np.linspace(0.0, 2.0 * math.pi, SEGMENTS, endpoint=False)
    z0, z1 = -width_mm / 2.0, width_mm / 2.0

    vertices: list[list[float]] = []
    for angle in angles:
        c, s = math.cos(angle), math.sin(angle)
        vertices.extend([
            [inner * c, inner * s, z0],
            [outer * c, outer * s, z0],
            [inner * c, inner * s, z1],
            [outer * c, outer * s, z1],
        ])

    faces: list[list[int]] = []
    for index in range(len(angles)):
        a, b = 4 * index, 4 * (index + 1)
        b %= 4 * len(angles)
        faces.extend([
            [a, b, b + 2], [a, b + 2, a + 2],              # inner wall
            [a + 1, a + 3, b + 3], [a + 1, b + 3, b + 1],  # outer wall
            [a, a + 1, b + 1], [a, b + 1, b],              # lower face
            [a + 2, b + 2, b + 3], [a + 2, b + 3, a + 3],  # upper face
        ])
    mesh = trimesh.Trimesh(vertices=np.asarray(vertices), faces=np.asarray(faces), process=True)
    trimesh.repair.fix_normals(mesh)
    return mesh


def placed_clip(side: int) -> trimesh.Trimesh:
    """Place one clip; ``side`` is -1 for left or +1 for right."""
    clip = annular_clip()
    rotation = trimesh.transformations.rotation_matrix(
        math.radians(side * OUTWARD_TILT_DEG), [0.0, 1.0, 0.0]
    )
    clip.apply_transform(rotation)
    clip.apply_translation([side * AXIS_SPACING_MM / 2.0, 0.0, AXIS_HEIGHT_MM])
    return clip


def build_holder() -> trimesh.Trimesh:
    clip_outer = BORE_DIAMETER_MM / 2.0 + WALL_MM
    bridge_length = AXIS_SPACING_MM + 2.0 * clip_outer
    bridge = _box(
        (bridge_length, BRIDGE_DEPTH_MM, BRIDGE_HEIGHT_MM),
        (0.0, BRIDGE_REAR_Y_MM, AXIS_HEIGHT_MM),
    )
    stem_top = AXIS_HEIGHT_MM - BRIDGE_HEIGHT_MM / 2.0 + 1.0
    stem_bottom = BASE_HEIGHT_MM - 1.0
    stem = _box(
        (STEM_WIDTH_MM, STEM_DEPTH_MM, stem_top - stem_bottom),
        (0.0, BRIDGE_REAR_Y_MM, (stem_top + stem_bottom) / 2.0),
    )
    foot_x = _box(
        (BASE_ARM_LENGTH_MM, BASE_ARM_WIDTH_MM, BASE_HEIGHT_MM),
        (0.0, BRIDGE_REAR_Y_MM, BASE_HEIGHT_MM / 2.0),
    )
    foot_y = _box(
        (BASE_ARM_WIDTH_MM, BASE_ARM_LENGTH_MM, BASE_HEIGHT_MM),
        (0.0, BRIDGE_REAR_Y_MM, BASE_HEIGHT_MM / 2.0),
    )
    solids = [placed_clip(-1), placed_clip(1), bridge, stem, foot_x, foot_y]
    holder = trimesh.boolean.union(solids, engine="manifold")
    if isinstance(holder, list):
        holder = trimesh.util.concatenate(holder)
    holder.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(holder)
    return holder


def body_clearance(body_diameter_mm: float = 50.0, below_clip_mm: float = 65.0) -> float:
    """Minimum nominal gap between equal LNBF bodies below the clip plane."""
    separation = AXIS_SPACING_MM - 2.0 * below_clip_mm * math.sin(math.radians(OUTWARD_TILT_DEG))
    return separation - body_diameter_mm


def main() -> None:
    holder = build_holder()
    coupon = annular_clip(width_mm=10.0)
    holder_path = HERE / "LT3D-001A-dual-lnbf-stand.stl"
    coupon_path = HERE / "LT3D-001B-lnbf-ring-fit-test.stl"
    holder.export(holder_path)
    coupon.export(coupon_path)

    gap = body_clearance()
    print(f"wrote {holder_path.name}: {holder.volume / 1000.0:.1f} cm³")
    print(f"wrote {coupon_path.name}: {coupon.volume / 1000.0:.1f} cm³")
    print(f"neck axes: {AXIS_SPACING_MM:.1f} mm apart, ±{OUTWARD_TILT_DEG:.1f}° outward")
    print(f"nominal Ø50 body gap 65 mm below clips: {gap:+.1f} mm")
    if gap < 0.0:
        print("WARNING: assumed Ø50 mm LNBF bodies overlap; verify the real body envelope")


if __name__ == "__main__":
    main()
