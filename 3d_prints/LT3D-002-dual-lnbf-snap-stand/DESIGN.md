# LT3D-002 — vertical dual-LNBF snap stand

## Released parts

| Part ID | File | Purpose |
| --- | --- | --- |
| `LT3D-002A` | `LT3D-002A-dual-lnbf-snap-stand.stl` | Complete stand for two vertical LNBFs |
| `LT3D-002B` | `LT3D-002B-lnbf-snap-fit-test.stl` | 10 mm-wide clip fit coupon |

This is the snap-in alternative to `LT3D-001`. Both Ø40 mm nominal LNBF neck
axes are vertical and remain 80 mm center-to-center. Each holder is a 242°
C-clip with a 118° side-entry gap, so an LNBF can snap radially into place.

## Fit and print contract

- Bore: Ø39.9 mm nominal; clip width: 24 mm.
- Neck axes: 80 mm apart, 0° outward tilt.
- The clip mouth is approximately 34.2 mm wide; it provides the retained
  snap-in gap rather than the closed-ring arrangement in `LT3D-001`.
- Assumed Ø50 mm LNBF bodies have 30 mm nominal clearance below the clips.

Print `LT3D-002B` first. If the fit is correct, print `LT3D-002A` with its
crossed foot on the build plate, using build-plate supports beneath clip arms.
PETG or ASA, 0.2 mm layers, four perimeters, and 25% infill are a reasonable
starting point.

## Regenerate and verify

```bash
uv run --with numpy --with trimesh --with manifold3d python generate.py
uv run --with numpy --with trimesh --with manifold3d --with scipy --with pytest pytest test_mesh.py -v
```
