# Position hypotheses from two independent Doppler shapes

**No conditioned in-tile hypothesis survived on any of the six offers.** The blind receiver found 3–47 geometrically in-tile intersections per offer before checking precision. The best of those pairs still had **42.19–52.71 km** worst-axis uncertainty, against a **35 km** proposal limit. It withheld before position refinement in both calibration arms. No estimate or forced coordinate was made. [Pair geometry and held RF figure](pass-support.png) · [Standard position and reference charts](charts/manifest.json) · [Scored evidence](scores.csv)

## Minimal constraints

The receiver links anonymous native GLRT within separate 30 s blocks. It keeps up to two arcs per block and sixteen measured points per arc. Every third block is held. Each anonymous candidate orbit supplies an exact local ECEF Doppler shape, an analytic east/north derivative and a profiled linearized orbital phase with a 6 s prior. A free affine frequency term removes constant LO, linear drift and the fixed-carrier contribution of `c`. This makes the two calibration arms identical. The leading eigenvector of the profiled spatial information becomes one line in tangent-plane position. The 280 Hz reference scale determines the pair conditioning. Candidate angles must have sine at least 0.45, and their time blocks and tentative NORADs must differ. [Frozen protocol](PROTOCOL.md) · [Source closure](source-lock.json)

The implementation generates continuous line intersections and would retain eight separated training-ranked seeds for exact geometry and small robust refinement. A mirrored control reflects those same intersections through the supplied tile centre and uses the same ranking and refinement. The earlier `pass_geometry` method extrapolates closest approach and votes single-pass geographic proposals into a mesh. The derivative and joint pass-identity prototypes score pooled shapes or use frame epochs to fit selected owners. This study constructs each position hypothesis from two separate measured-interval constraints with no position mesh. Distinct timed candidate NORADs ensure the method avoids deliberately reusing a nominal owner. The anonymous labels remain inferred. [Original predictions](positions.jsonl.gz)

## What stopped the geometry

| Offer | Independent pairs | Angle eligible | Raw in-tile intersections | Best in-tile σ (km) | Median line strength affine / offset-only (Hz/km) |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0168, containing | 1,335 | 902 | 46 | 44.08 | 6.53 / 23.61 |
| DS29-0519, containing | 1,322 | 883 | 47 | 42.19 | 6.52 / 14.16 |
| DS26-0070, omitted | 1,323 | 864 | 17 | 43.71 | 6.50 / 12.52 |
| DS29-0316, omitted | 1,330 | 888 | 7 | 47.05 | 6.47 / 10.79 |
| Waveform containing | 384 | 243 | 16 | 52.71 | 5.52 / 6.68 |
| Waveform omitted | 384 | 239 | 3 | 52.41 | 5.52 / 6.68 |

Two pairs passed the angle and 35 km tests without the tile bound. Both intersections lay outside their offers. Every raw in-box intersection was too weak even under this optimistic two-line local uncertainty. The offset-only diagnostic reused exactly the same candidates, measured times and phase nuisance. Removing the additional affine clock slope sharply reduced real-site line strength, while eliminating more of the unknown receiver term. The offset-only comparison measures geometry under a narrower nuisance model and carries no evidence that the real receiver satisfies that model. [Conditioning protocol](CONDITIONING-PROTOCOL.md) · [Exact pair and RF audit](conditioning.json)

The frozen seed gate prevented the full and mirrored branches from producing sites to compare. The separate diagnostic evaluated a fixed centre and ±8 km east/west reflection without using those sites as predictions. At each point it used held block prefixes to select phase, affine clock and an orbit absent from trained support, then measured late RF. The tile centres supplied **1–3** supported held candidate families and **276–1,096 Hz** held shape RMS. The conditioning and RF audit was sealed before geographic scoring. [Audit seal](conditioning-lock.json)

## Matched geography and resources

Original no-repair v5 published at **1.52 and 0.25 km** in c0 on the two real containing offers, whose tile centres were 8.19 km from truth. All four original v5 choices are shown only on those authentic inputs. The installed waveform comparison points to the original emitted stock-detector data from the independent simulated site. Its containing and omitted c0 estimates were 1.02 and 1.58 km. The primary receiver and mirror control both withheld on the two real omitted offers and the waveform omitted offer. [Per-query geography and conditional RF](scores.csv) · [Waveform source study](../../track-recovery/waveform-site/README.md)

The first position charts classified these completed receiver decisions as stage-only because the gate prevented numerical refinement. The corrected charts count the receiver's recorded terminal decisions as withheld and retain the no-refinement flag and both null endpoints. A chart-only manifest authenticates each copied decision against the original prediction archive. The original predictions, source, scores and fixed-site RF evidence retain their original seals. [Terminal decision manifest](terminal-decisions.json) · [Corrected chart specification](figures.json)

Each real offer supplied 20 arcs and 56 training lines. Each waveform offer supplied 12 arcs and 32 training lines. The 328-line receiver had a median **1.68 s CPU** and **3.20 s elapsed** on the six primary jobs. The largest peak RSS was **184.4 MiB** under the 512 MiB limit. The diagnostic was a separate replay of the same raw input and constraint inventory and never modified the primary position archive. The main unresolved variable is whether longer independently supported arcs, or a physically authenticated shared oscillator slope, can carry enough shape information for a conditioned pair. [Input roster](blind-plan.json) · [Prediction seal](prediction-lock.json) · [Scored artifacts](score-lock.json)
