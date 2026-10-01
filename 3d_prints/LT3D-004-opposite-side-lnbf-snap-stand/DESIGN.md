# LT3D-004: opposite-side snap stand

One LNB sits on each side of the central bridge, diagonally opposed. Both feeds
point upward and tilt apart in the X/Z plane. The two snap openings face away
from the bridge, allowing independent insertion from the front and back.
LT3D-003 remains the same-side alternative.

The proven LT3D-002 clip boundary is retained exactly: 39.9 mm bore, 4.5 mm wall,
24 mm axial width and 242° arc. One clip is rotated 180° about its local axis
before tilting. This rotates the holder opening; it does not prescribe LNB
polarization roll. Set and record each receiver's roll separately.

| Part | Included feed-axis angle | Individual tilt | Footprint | Height |
| --- | --- | --- | --- | --- |
| LT3D-004A | 30° | ±15° | 150 × 150 mm | 132.92 mm |
| LT3D-004B | 40° | ±20° | 150 × 150 mm | 134.64 mm |

Neck centers are 115 mm above the base, separated by 89.443 mm along X and
80 mm along Y: 120 mm diagonally. This changes the receiver baseline direction;
record the new physical positions in acquisition metadata. Moving the receivers
across the bridge alone does not change sky coverage when their pointing axes
are unchanged.

## Files and validation

Print the `*-snap-stand.stl` files; matching STEP files are editable solids.
`*-ASSUMED-wide60-assembly.step` contains the mount and illustrative LNB bodies.
The assembly bodies are **not exact Geostar or Edision models**. Manufacturer
STEP search provenance and rejected Norsat references remain in LT3D-003.
The optional LT3D-004C coupon repeats the established fit profile at 10 mm width.

The assumed envelopes have a 40 mm neck spanning local Z=-18…18 mm, a 60 mm
feed head at Z=18…42 mm, and either a 50 mm body extending to Z=-65 mm or a
60 mm body extending to Z=-75 mm. A 12 mm diameter connector extends another
20 mm rearward. Cable bends, boots and non-cylindrical projections are excluded.

| Wide-body envelope check | 30° | 40° |
| --- | --- | --- |
| Between receiver envelopes | 35.27 mm | 29.33 mm |
| Minimum non-neck clearance to mount | 4.78 mm | 2.45 mm |
| Lowest connector above base plane | 21.68 mm | 23.68 mm |

Both variants are valid single solids. Tests check the exact original snap
vertices, axis angles and spacing, outward openings, watertight STL meshes,
STEP round-trip volume, body clearance and sampled insertion paths with the
other receiver seated. Neck interference is intentional: a 40 mm nominal neck
in the existing 39.9 mm snap bore. These are geometric checks, not a simulation
of clip flex, wind loading, tipping or cable forces. Actual body fit is still
conditional on receiver dimensions. Use slicer support beneath the elevated
bridge and tilted clips as needed; avoid support damage to the snap surfaces.

## Reproduce

From the repository root:

```sh
uv run --no-project --with cadquery==2.8.0 --with numpy --with trimesh --with matplotlib python 3d_prints/LT3D-004-opposite-side-lnbf-snap-stand/generate.py
uv run --no-project --with cadquery==2.8.0 --with numpy --with trimesh --with pytest python -m pytest 3d_prints/LT3D-004-opposite-side-lnbf-snap-stand/test_design.py -q
```

`verification.json` records measured geometry. `top-view.png`, `mounts.png` and
`assemblies.png` show the opposing layout and the two angles.
