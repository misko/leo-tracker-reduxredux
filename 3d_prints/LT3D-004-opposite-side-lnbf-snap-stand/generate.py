"""LT3D-004: 30/40-degree stands retaining LT3D-002's polygonal snap fit.

Run with uv run --no-project --with cadquery==2.8.0 --with numpy --with trimesh
--with matplotlib python generate.py. All lengths are mm; +Z is the feed axis.
Reference envelopes are assumptions, not manufacturer CAD of the user's LNBs.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import cadquery as cq
import numpy as np

HERE = Path(__file__).resolve().parent
BORE_DIAMETER_MM = 39.9
WALL_MM = 4.5
CLIP_WIDTH_MM = 24.0
CLIP_SWEEP_DEG = 242.0
SEGMENTS = 160
AXIS_SPACING_MM = 120.0
AXIS_HEIGHT_MM = 115.0
Y_OFFSET_MM = 40.0
X_SPACING_MM = math.sqrt(AXIS_SPACING_MM**2 - (2*Y_OFFSET_MM)**2)
VARIANTS = {"LT3D-004A": 30.0, "LT3D-004B": 40.0}
ENVELOPES = {
    "compact-50": {"body_diameter_mm": 50.0, "rear_extent_mm": 65.0},
    "wide-60": {"body_diameter_mm": 60.0, "rear_extent_mm": 75.0},
}


def box(x, y, z, center):
    return cq.Workplane("XY").box(x, y, z).translate(center).val()


def cylinder(radius, zmin, zmax):
    return cq.Solid.makeCylinder(radius, zmax-zmin, cq.Vector(0, 0, zmin))


def snap_clip(width=CLIP_WIDTH_MM):
    """Identical boundary vertices to the proven LT3D-002 snap clip."""
    angles = np.linspace(math.radians(149), math.radians(391), SEGMENTS)
    inner, outer = BORE_DIAMETER_MM/2, BORE_DIAMETER_MM/2+WALL_MM
    points = [(outer*math.cos(a), outer*math.sin(a)) for a in angles]
    points += [(inner*math.cos(a), inner*math.sin(a)) for a in angles[::-1]]
    return cq.Workplane("XY").polyline(points).close().extrude(width).translate((0, 0, -width/2)).val()


def place(shape, side, included_angle, spacing=AXIS_SPACING_MM, height=AXIS_HEIGHT_MM):
    if side not in (-1, 1) or included_angle not in (30, 40):
        raise ValueError("Expected side -1/+1 and 30/40 degree included angle")
    # Reverse one clip's opening without reversing its upward feed axis.
    shape = shape.rotate((0, 0, 0), (0, 0, 1), 180 if side == -1 else 0)
    x_spacing = math.sqrt(spacing**2 - (2*Y_OFFSET_MM)**2)
    return shape.rotate((0, 0, 0), (0, 1, 0), side*included_angle/2).translate((side*x_spacing/2, side*Y_OFFSET_MM, height))


def holder(angle):
    clips = [place(snap_clip(), s, angle) for s in (-1, 1)]
    # A 12 mm bridge clears the tilted 60 mm shoulder at both axial ends.
    bridge = box(X_SPACING_MM+48.9, 37, 12, (0, 0, AXIS_HEIGHT_MM))
    stem = box(20, 18, 101, (0, 0, 59.5))  # z=9..110
    foot_x = box(150, 20, 10, (0, 0, 5))
    foot_y = box(22, 150, 10, (0, 0, 5))
    result = clips[0].fuse(clips[1], bridge, stem, foot_x, foot_y).clean()
    # Back-side base marking identifies angle without touching clip surfaces.
    label = (cq.Workplane("XY").text(str(int(angle)), 8, 1.2, combine=False)
             .translate((60, 0, 9.8)))
    for solid in label.vals():
        result = result.fuse(solid)
    return result.clean()


def reference_parts(name):
    """A 40-mm neck plus two rotationally symmetric body-envelope scenarios.

    The neck/body/head stations and connector are assumptions. Rotationally
    symmetric envelopes avoid implying that an unrecorded roll was measured.
    """
    p = ENVELOPES[name]
    rear = p["rear_extent_mm"]
    return {
        "neck": cylinder(20, -18, 18),
        "body": cylinder(p["body_diameter_mm"]/2, -rear, -18),
        "feed_head": cylinder(30, 18, 42),
        "connector": cylinder(6, -rear-20, -rear),
    }


def reference_shape(name):
    parts = list(reference_parts(name).values())
    return parts[0].fuse(*parts[1:]).clean()


def volume_common(a, b):
    return sum(s.Volume() for s in a.intersect(b).Solids())


def bounds(shape):
    b = shape.BoundingBox()
    return {"min": [b.xmin, b.ymin, b.zmin], "max": [b.xmax, b.ymax, b.zmax],
            "size": [b.xlen, b.ylen, b.zlen]}


def verify_assembly(mount, angle, name):
    refs = [place(reference_shape(name), s, angle) for s in (-1, 1)]
    result = {"pair_gap_mm": refs[0].distance(refs[1]),
              "pair_intersection_mm3": volume_common(*refs), "receivers": []}
    for side, ref in zip((-1, 1), refs, strict=True):
        pieces = reference_parts(name)
        obstacles = [place(v, side, angle) for k, v in pieces.items() if k != "neck"]
        neck = place(pieces["neck"], side, angle)
        result["receivers"].append({
            "side": side, "minimum_z_mm": bounds(ref)["min"][2],
            "non_neck_mount_gap_mm": min(p.distance(mount) for p in obstacles),
            "non_neck_intersection_mm3": sum(volume_common(p, mount) for p in obstacles),
            "neck_interference_mm3": volume_common(neck, mount),
            "connector_mount_gap_mm": obstacles[-1].distance(mount),
        })
    return result


def assembly(mount, angle, name):
    out = cq.Assembly(name=f"LT3D-004-{int(angle)}deg-{name}-ASSUMED")
    out.add(mount, name="print_mount_only", color=cq.Color(.23, .48, .66))
    for side in (-1, 1):
        for part_name, shape in reference_parts(name).items():
            color = cq.Color(.85, .85, .82) if part_name == "feed_head" else cq.Color(.28, .29, .30)
            if part_name == "connector":
                color = cq.Color(.77, .64, .28)
            out.add(place(shape, side, angle), name=f"assumed_{side}_{part_name}", color=color)
    return out


def render(mounts):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    def draw(ax, shape, color):
        vertices, faces = shape.tessellate(.25, .25)
        v = np.array([p.toTuple() for p in vertices])
        ax.add_collection3d(Poly3DCollection(v[np.array(faces)], facecolors=color, shade=True, linewidths=0))

    for assembled in (False, True):
        fig = plt.figure(figsize=(12, 6))
        for i, (part, angle) in enumerate(VARIANTS.items(), 1):
            ax = fig.add_subplot(1, 2, i, projection="3d")
            draw(ax, mounts[part], "#4f92b6")
            if assembled:
                for side in (-1, 1):
                    for name, shape in reference_parts("wide-60").items():
                        color = "#e0ded5" if name == "feed_head" else "#65666a"
                        if name == "connector":
                            color = "#c49d3b"
                        draw(ax, place(shape, side, angle), color)
            ax.set(xlim=(-110, 110), ylim=(-90, 90), zlim=(0, 180 if assembled else 140),
                   title=f"{part} · {int(angle)}° total · 120 mm spacing",
                   xlabel="X (mm)", ylabel="Y (mm)", zlabel="Z (mm)")
            ax.set_box_aspect((220, 180, 180 if assembled else 140))
            ax.view_init(22, 55)
        fig.suptitle("Opposite-side LNBs · outward snap openings", fontsize=17)
        caption = ("Shown with assumed Ø60 mm bodies and 40 mm necks; not exact Geostar/Edision models."
                   if assembled else "Original LT3D-002 snap geometry preserved: Ø39.9 mm bore, 242° arc, 24 mm width.")
        fig.text(.5, .025, caption, ha="center", fontsize=11)
        fig.tight_layout(rect=(0, .06, 1, .95))
        fig.savefig(HERE / ("assemblies.png" if assembled else "mounts.png"), dpi=170)
        plt.close(fig)


def render_plan(mounts):
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    for ax, (part, angle) in zip(axes, VARIANTS.items()):
        vertices, faces = mounts[part].tessellate(.25, .25)
        v = np.array([p.toTuple() for p in vertices])
        triangles = v[np.array(faces)]
        triangles = triangles[np.argsort(triangles[:, :, 2].mean(axis=1))]
        colors = ["#81afc6" if t[:, 2].mean() > 100 else "#d5e2e9" for t in triangles]
        ax.add_collection(PolyCollection(triangles[:, :, :2], facecolors=colors, linewidths=0))
        for side in (-1, 1):
            x, y = side*X_SPACING_MM/2, side*Y_OFFSET_MM
            ax.plot(x, y, "o", color="#172a3a")
            ax.annotate("snap outward", xy=(x, side*88), xytext=(x, side*64),
                        ha="center", fontsize=9, arrowprops=dict(arrowstyle="->"))
        ax.set(xlim=(-90, 90), ylim=(-100, 100), aspect="equal",
               xlabel="X (mm)", ylabel="Y (mm)", title=f"{part} · {int(angle)}°")
        ax.grid(alpha=.15)
    fig.suptitle("Top view: one LNB on each side of the central bridge", fontsize=16)
    fig.text(.5, .02, "Neck centers: 80 mm front/back, 89.44 mm left/right; 120 mm diagonal spacing.",
             ha="center")
    fig.tight_layout(rect=(0, .05, 1, .94))
    fig.savefig(HERE / "top-view.png", dpi=170)
    plt.close(fig)

def main():
    output = {"status": "prototype; actual Geostar/Edision body dimensions unverified",
              "cadquery_version": cq.__version__, "variants": {}, "references": {}}
    (HERE / "envelopes").mkdir(exist_ok=True)
    for name in ENVELOPES:
        cq.exporters.export(reference_shape(name), str(HERE / "envelopes" / f"ASSUMED-{name}.step"))
    mounts = {}
    for part, angle in VARIANTS.items():
        mount = holder(angle)
        assert mount.isValid() and len(mount.Solids()) == 1
        mounts[part] = mount
        stem = f"{part}-{int(angle)}deg-snap-stand"
        cq.exporters.export(mount, str(HERE / f"{stem}.step"))
        cq.exporters.export(mount, str(HERE / f"{stem}.stl"), tolerance=.05, angularTolerance=.08)
        checks = {name: verify_assembly(mount, angle, name) for name in ENVELOPES}
        for result in checks.values():
            assert result["pair_gap_mm"] >= 5 and result["pair_intersection_mm3"] < 1e-6
            for rx in result["receivers"]:
                assert rx["non_neck_intersection_mm3"] < 1e-6
                assert rx["non_neck_mount_gap_mm"] >= 2
                assert rx["minimum_z_mm"] >= 10
        output["variants"][part] = {"included_angle_deg": angle, "spacing_mm": AXIS_SPACING_MM,
            "axis_height_mm": AXIS_HEIGHT_MM, "x_spacing_mm": X_SPACING_MM, "y_spacing_mm": 2*Y_OFFSET_MM, "mount_bounds_mm": bounds(mount),
            "mount_volume_cm3": mount.Volume()/1000, "checks": checks}
        assembly(mount, angle, "wide-60").export(str(HERE / f"{part}-ASSUMED-wide60-assembly.step"))
    cq.exporters.export(snap_clip(10), str(HERE / "LT3D-004C-snap-fit-test.stl"), tolerance=.05)
    render(mounts)
    render_plan(mounts)
    (HERE / "verification.json").write_text(json.dumps(output, indent=2)+"\n")
    print(json.dumps(output["variants"], indent=2))


if __name__ == "__main__":
    main()

