# Can orbital curvature explain the saved double-difference fluctuations?

The earlier `scan-hop-28d7592ea614f624` matched-pilot analysis has thirteen accepted visits on its fixed RF path. Their phase fluctuations exceed the conditional within-visit bootstrap uncertainty. This follow-up checks whether ordinary orbital curvature alone can explain those values, interpreted as phase at the published measurement centers.

For the fastest previously illustrated circular orbit (350 km) and largest illustrated RF baseline (114.73 mm), an orientation-independent bound on two-source geometric phase acceleration is **5.242 degrees/s²** at 11.4596875 GHz. All eleven consecutive three-visit interpolation residuals exceed this scenario's noise-free geometric bound. The discrepancy still requires measurement/channel terms or a failure of the scenario assumptions; it is not evidence that the instruments physically changed phase.

The largest required uniform point correction is **5.32 degrees**: at least one measurement in visits 1085/1093/1105 must differ from any admissible geometric point-phase trajectory by that much. This is a deterministic compatibility calculation, not a confidence interval. The existing several-degree repeatability errors can be material here. It does not identify which visit is wrong or prove that the sources are satellites.

## Bound and assumptions

Let the satellite-to-observer displacement be `r`, range `rho`, and line of sight `s = r/rho`. In an inertial frame,

`s' = (I - ssᵀ) r' / rho`,

`s'' = (I - ssᵀ) r''/rho - 2(rho'/rho)s' - s|s'|²`.

Consequently `|s'| <= V/h` and `|s''| <= A/h + 3(V/h)²` when the relative speed and acceleration are bounded by V and A, and range is at least h. For a spherical Earth, a circular orbit at altitude h, and a fixed terrestrial observer with radius no greater than R,

`V = sqrt(mu/(R+h)) + Omega*R`,

`A = mu/(R+h)² + Omega²*R`.

A baseline fixed to Earth has `|b'| <= Omega|b|` and `|b''| <= Omega²|b|`. Differentiating `G = (360*f/c) b·s` twice gives the single-source bound

`|G''| <= (360*f*|b|/c) [A/h + 3(V/h)² + 2*Omega*V/h + Omega²]`.

Summing two single-source bounds bounds their difference. This calculation allows any baseline orientation, satellite headings, or source angular separation. It assumes circular orbits, fixed carrier frequency, fixed RF phase centers, a rigid ground fixture, and a spherical Earth. The recorded station altitude is -29 m, so using R as its radius bound is conservative. The RF baseline is a sensitivity case derived from the STL plus 100-mm equal axial phase-center offsets, **not a measured upper bound on the installed RF baseline**. This is not a universal exclusion of all orbits or channel models.

If `|G''| <= B`, the middle point's departure from linear interpolation between neighboring points at gaps h1 and h2 obeys `|residual| <= B*h1*h2/2`. If every measured phase differs from the physical curve by at most e, its interpolation residual can change by at most 2e. Hence `max(0, |residual|-bound)/2` is a lower bound on the largest absolute point correction needed for that triple. The bound applies after a consistent phase branch is established. For these data, the corresponding maximum rate (73.867 degrees/s for the double difference) excludes alternative 360-degree steps between accepted visits under the noise-free point model.

## Representative results

| Visits | Absolute interpolation residual | Geometric bound | Minimum uniform point correction |
|---|---:|---:|---:|
| 1085 / 1093 / 1105 | 14.72° | 4.09° | 5.32° |
| 1105 / 1109 / 1113 | 9.48° | 0.67° | 4.40° |
| 1124 / 1128 / 1132 | 6.64° | 0.70° | 2.97° |
| 1132 / 1136 / 1140 | 9.06° | 0.68° | 4.19° |

These are not independent significance tests. Bootstrap error, estimator bias, source misassociation, source-dependent transfer, and any discrepancy between finite-window phase estimates and their stated point centers remain unresolved. The calculation does not silently treat those terms as zero when making a physical claim. It shows why the observed fluctuations cannot simply be labelled expected orbital motion on this scenario.

## Evidence and reproduction

- Input: [matched-pilot cohort report](2026_09_21_scan_hop_28d_matched_pilot_dd_cohort.md); canonical input digest `sha256:000e77ba1419de0bd55b45a71cb44584d8954584bd8e1b3ba1b3ae871173821c`.
- Output: [all eleven triplets](figures/2026_09_21_phase_curvature_bound/scan28d-curvature-bound-v1.json); canonical digest `sha256:5113f5055f8aa5ac848fe94d094c9b94f23a2281e2eef3ebf656d6e4fe28f00c`.
- Tool: `tools/report_phase_curvature_bound.py --input <cohort.json> --json <output.json>` verifies the input digest before calculating results.
- Tests check the sharp interpolation bound against a known quadratic and the derivative bound against finite differences of independently propagated circular orbits, with randomized orientations and headings across four altitude classes (3 tests pass).

No saved IQ was changed and no RF was collected. The goal of recovered geometric phase remains unproven.
