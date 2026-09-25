# LT3D-001 — dual-LNBF free-standing holder

## Released parts

| Part ID | File | Purpose |
| --- | --- | --- |
| `LT3D-001A` | `LT3D-001A-dual-lnbf-stand.stl` | Complete free-standing holder for two LNBFs |
| `LT3D-001B` | `LT3D-001B-lnbf-ring-fit-test.stl` | 10 mm-wide fit coupon for one LNBF neck |

`LT3D-001A` holds two Ø40 mm nominal LNBF necks at 80 mm center-to-center.
Each neck axis points 10° outward from the vertical centerline, for a 20°
included angle. The stand consists of two closed circular rings, a rear bridge,
a central stem, and a crossed foot.

## Fit and installation contract

- Ring bore: Ø39.9 mm nominal.
- Ring width: 24 mm along the LNBF axis.
- Holder spacing: 80 mm between ring axes.
- Foot: crossed, 82 mm overall arm length and 10 mm thick.
- Ring form: **closed 360° ring**. It is not a snap-fit; install each LNBF
  axially before a feedhorn or body feature prevents passage.
- The rear bridge sits entirely behind the bore boundary. It must never create
  a chord or flat inside either circular neck opening.

At 65 mm below the rings, the nominal clearance between two assumed Ø50 mm
LNBF bodies is 7.4 mm. Measure the actual LNBF body envelope before printing;
larger bodies or a longer reference distance may require a new design family.

## Printing

Print `LT3D-001A` with the crossed foot on the bed. Build-plate supports are
required below the ring overhangs. PETG or ASA is preferable outdoors. Start
with 0.2 mm layers, four perimeters, and 25% infill.

Print `LT3D-001B` first and confirm axial neck fit before committing to the
full stand.

## Regeneration and verification

```bash
uv run --with numpy --with trimesh --with manifold3d python generate.py
uv run --with numpy --with trimesh --with manifold3d --with scipy --with pytest pytest test_mesh.py -v
```

The tests verify that the holder is one watertight printable body, has a flat
base, retains the released geometry contract, keeps its bridge outside both
bores, and has positive nominal body clearance.

## Receiver geometry authority

The content-addressed station record
[`deploy/station/gauss-r21-lt3d-001a-20260920-v1.json`](../../deploy/station/gauss-r21-lt3d-001a-20260920-v1.json)
records the nominal slot mount references and neck axes in metres using a local
right/front/up frame. It binds `LT3D-001A` to radio `.21` by stable radio serial
and physical receiver IDs without changing the published recording manifest.

The authority deliberately leaves RF phase-centre positions and RF boresights
unset. The holder CAD does not establish either quantity; they require LNBF
measurements or manufacturer evidence before geometry-aware RF analysis may use
them.

The current RX0/RX1-to-left/right assignment is marked `provisional` because a
physical cable trace has not been recorded. Geometry-aware analysis must retain
that status and must not interpret the sign of the baseline until an operator
publishes a new authority revision with a verified mapping. The 80 mm baseline
length and 20° included boresight angle are unaffected by swapping the slots.
