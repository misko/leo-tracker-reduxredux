# Measured transfer and beacon observability

The checked archives exposed zero compatible independent wideband captures with both Qin-pilot coverage and the required location, clock and causal-orbit authority. On a separate one-band beacon control, giving the receiver the author’s site-assisted satellite identities made the containing tile fit better on all six StarLoc sites with measurable simultaneous contrast. Only two met the 5 km local conditioning diagnostic, and one of those two forced coordinates was 9.35 km from its receiver. The remaining two sites have zero common-clock contrast. [Source inventory](source-inventory.md) · [Matched measurements and scores](scores.json)

## What the measured control establishes

StarLoc’s eleven captures cover eight physically distinct measured locations using the same external three-channel instrument. This experiment uses the first capture in each group, the already sealed correct and omitted 25 km tiles, measured `main_tone_dict` time and Hz, and the same per-capture causal orbit text. Every author `id_dict` name in the selected capture records maps unambiguously to a causal orbit. The authors’ orbit labels are site-assisted. The isolated fit receives one offer at a time and the supplied labels, while GNSS coordinates, calibrated phase and antenna orientation remain in the evaluator. Catalogue availability at capture start is author-reported. [StarLoc report](https://arxiv.org/html/2604.21147v1#S4.SS2) · [Pinned MAT variable contract](https://raw.githubusercontent.com/GiddaZhang/Starloc/fc010f950dfac5ac6d7a345db24513217fbb81d5/data/README.md) · [Frozen site and orbit authority](../../../2026_11_18_blind_regional_receiver/field_private/provenance.md)

The model subtracts the exact causal orbit Doppler and removes two nuisance terms jointly, a free additive receiver frequency at each simultaneous epoch and a constant level for each arc. An epoch with only one visible arc supplies zero independent frequency evidence under that model. The fit uses all retained exact intersections after half-second thinning. It selects location on 4 s training blocks and evaluates disjoint held blocks at the same location. On a single nominal RF, a constant `c` is absorbed by the projected nuisance terms, so both calibration arms are identical. The report compares RMS in Hz with horizontal error in km separately. [Frozen protocol](PROTOCOL.md)

| Offer | Attempts | Finite held fits | Median held RF RMS | Median forced horizontal error | Median center error on same six sites | Held position scale ≤5 km |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Containing | 8 | 6 | 96.6 Hz | 6.75 km | 8.43 km | 2 of 6 |
| Receiver omitted | 8 | 6 | 586.0 Hz | 124.71 km | 139.79 km | 2 of 6 |

Three forced containing coordinates were within 5 km of GNSS, and three improved on their tile centers. Both successful local conditioning diagnostics also passed in those same sites’ omitted tiles, so local curvature alone cannot reject an incorrect offer. A quantization-only error model suggests 5 km local conditioning on four sites. Using the actual held residual scale of the other sites reduces that count to two. The site-excluded scales were 95.8–97.5 Hz. This Jacobian calculation assumes independent errors and supplies a conditioning diagnostic. It gives no calibrated error coverage for correlated receiver and orbit mismatch. [Per-site numerical receipt](scores.json)

| Physical site | `c = 0` and fitted `c` held rank | Containing held RF RMS | Omitted held RF RMS | Containing forced error | Containing site-excluded local scale |
| --- | ---: | ---: | ---: | ---: | ---: |
| 01 | 15 | 97.5 Hz | 226.6 Hz | 4.15 km | 14.07 km |
| 02 | 5 | 95.8 Hz | 115.0 Hz | 15.67 km | 888.15 km |
| 03 | 22 | 94.3 Hz | 2,061.9 Hz | 3.62 km | 6.79 km |
| 04 | 42 | 86.6 Hz | 1,187.7 Hz | 9.35 km | 2.48 km |
| 05 | 0 | — | — | — | — |
| 06 | 32 | 121.0 Hz | 147.5 Hz | 2.96 km | 4.94 km |
| 07 | 0 | — | — | — | — |
| 08 | 21 | 119.2 Hz | 945.4 Hz | 13.64 km | 220.77 km |

Both position arms are evaluator controls and all 16 publication decisions withhold. The earlier anonymous coincidence run found competing orbit assignments and sometimes comparable or better omitted-tile fits. Fixed labels isolate what geometry can contribute under the shared-clock model. This cohort supports coarse differentiation of these matched offers conditional on labels, weak local position evidence, and no independent wideband or blind identity generalization. Median isolated launch, import, propagation and fit wall time was 1.66 s for containing and 1.71 s for omitted queries. [Earlier anonymous experiment](../../inference/physical-differences/README.md) · [`c = 0` figure](position-errors-c0.png) · [Fitted `c` figure](position-errors-fitted_c.png)

## Reproduce

The sealed prediction archive binds the original MAT digest, causal catalogue, observation clock, one tile and byte-exact worker payload. `runner-at-measurement.py.gz` retains the exact predictor driver from its source lock. The live driver changes only scoring after prediction to read the existing sealed GNSS field `latlon`. The derived chart seal records the scorer’s digest as well.

```bash
# With an unpopulated report directory in a fresh checkout, and the eleven staged MAT files
nice -n 10 taskset -c 12,13 .venv/bin/python -B -m \
  tools.pipeline_eval.qualification.measured_transfer predict --raw "$STARLOC_MAT_ROOT"

# Score the sealed predictions in the report directory
.venv/bin/python -B -m tools.pipeline_eval.qualification.measured_transfer score
```
