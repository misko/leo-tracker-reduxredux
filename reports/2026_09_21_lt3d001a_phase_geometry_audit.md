# LT3D-001A geometry for shared-receiver phase recovery

Date: 2026-09-21. The released STL was read directly; the mesh and recording
geometry were not modified.

## Verified mesh

`3d_prints/LT3D-001-dual-lnbf-stand/LT3D-001A-dual-lnbf-stand.stl`
has SHA-256
`934d4fe7f26b4169f4f421e7383137f5eeb22317ae141bcdaf1fcf9e2221f487`,
matching the mesh digest in the recorded station geometry. The binary mesh
contains 2,876 triangles. Coordinates below are millimetres in the holder's
local right/front/up frame, as defined by its generator.

| Quantity | Negative-x slot | Positive-x slot |
| --- | --- | --- |
| Ring reference position | (-40, 0, 76) | (+40, 0, 76) |
| Neck-axis unit vector | (-0.17364818, 0, 0.98480775) | (+0.17364818, 0, 0.98480775) |
| Bore radius | 19.95 mm | 19.95 mm |
| Axial ring extent about reference | -12 to +12 mm | -12 to +12 mm |

For each slot, 1,920 triangle-vertex entries lie on the expected inner bore,
and 640 end-face triangles have normals parallel to the expected neck axis.
The ring spacing is 80 mm and the neck-axis included angle is 20 degrees.
These are actual mesh checks in addition to the design constants.

## RF phase-center baseline

Let `m0`, `m1` be the two mount reference positions and `a0`, `a1` their
neck axes. Parameterize the RF phase centers as

```text
p0 = m0 + d0*a0 + e0
p1 = m1 + d1*a1 + e1
b  = p1 - p0
```

Here `d0` and `d1` are the axial distances from the ring references to the
electrical phase centers; `e0` and `e1` allow non-axial offsets. This explicitly
uses the released CAD geometry without equating a mounting ring with an RF
phase center. For identical axial offsets `d` and zero non-axial offsets,

```text
b = (80 + 2*d*sin(10 degrees), 0, 0) mm.
```

Thus a hypothetical 50 mm axial offset would give a 97.36 mm RF baseline.
That example is a sensitivity calculation, not a measurement of these LNBs.
An installed rotation maps this local baseline into the sky coordinate frame.
Reversing the RX-to-slot assignment reverses its sign.

## Observable and identifiability

With `b = p_RX1 - p_RX0` and unit vector `s` pointing toward a source, the
far-field RX1-minus-RX0 geometric phase is

```text
phi_geom = (2*pi/lambda) * dot(b, s) modulo 2*pi.
```

The measured receiver phase also includes differential oscillator phase,
frequency-dependent receiver transfer phase, propagation/channel effects, and
estimation error. For two sources observed simultaneously by both receivers,
subtracting their receiver differences cancels a common oscillator term. The
result is a geometric double difference plus any non-common transfer/channel
terms. It is not the absolute path difference of either individual source.

The 20-degree mechanical divergence motivates allowing unmatched and partially
shared tracklets. It does not define an antenna beamwidth. Source overlap must
be qualified from simultaneous IQ before fitting phase; geometry must not be
used to choose whichever frequency or phase ambiguity matches a desired curve.

The STL establishes the holder-local mount positions and axes. Electrical
phase-center offsets, installed orientation, receiver-to-slot assignment,
source direction, and differential transfer calibration remain explicit
inputs or unknown parameters. The current recorded assignment is provisional.
No missing value is silently set to zero or treated as measured authority.
