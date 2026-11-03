# Fine DS8 timing profiles reveal an optimizer qualification failure

An independent scalar solver confirms a stronger timing solution in `scan-fw-5579ea7efd8c20da` at the original rank-start N40 location. The timing changes from **−0.289365 s to approximately −0.824590 s**, improving training log score by **2.995290** and held log score by **28.515677**. The original gradient optimizer reached that same peak but returned `ABNORMAL`, so the earlier qualification rule excluded it.

This identifies a concrete numerical limitation in timing search and qualification. It does not demonstrate a geographic accuracy improvement: geography stays fixed throughout this experiment.

## Profiles and independent check

The [protocol](PROTOCOL.md) selects the three scans whose timings differ by over 0.1 seconds between the original qualified N40 endpoints. Each is evaluated at the latest qualified corrected location and the original qualified rank location, using a 401-point grid at 0.025-second spacing across −5 to +5 seconds. Every detected local maximum receives refinement, as does the inherited timing. All source hashes and scalar/grid score replays pass.

| Scan suffix | Fixed location | Grid peaks | Training gain from independently validated best peak | Held gain |
|---|---|---:|---:|---:|
| 226485b45dd0d0cf | Corrected | 2 | <0.00000001 | +0.000062 |
| 226485b45dd0d0cf | Rank | 1 | <0.00000001 | +0.000039 |
| 2397fe2b6f23337a | Corrected | 2 | <0.00000001 | −0.000088 |
| 2397fe2b6f23337a | Rank | 2 | <0.00000001 | −0.000099 |
| 5579ea7efd8c20da | Corrected | 3 | <0.00000001 | −0.000001 |
| 5579ea7efd8c20da | Rank | 3 | +2.995290 | +28.515677 |

![Timing likelihood profiles](timing-profiles.png)

Each plotted curve is normalized to its own sampled maximum; their heights cannot compare the absolute scores of the two locations. Dotted lines show inherited timings. The figure zooms to the relevant peaks; full profiles include the much weaker near-5-second peak in the third scan.

The first stage took 13.93 seconds. Three gradient-optimizer refinements at the rank location for the third scan returned `ABNORMAL`, including the stronger peak. Its timing gradient was 0.00000214, with finite-difference discrepancy 0.000000143. These failed fits remain in [results.json](results.json) and are not retrospectively reclassified.

The separately declared [scalar protocol](SCALAR_PROTOCOL.md) then validates **all thirteen detected peaks**, using bounded one-dimensional minimization between adjacent grid points. All thirteen pass scalar success, gradient, finite-difference, global-boundary and grid-score checks. Held data do not select timing or qualification. [scalar-results.json](scalar-results.json) retains every result.

## What this changes

The strongest rank-location peak can be missed by taking only the best coarse-grid seed, and a valid alternative can be rejected because of an optimizer termination failure. An explicit bracketed solver offers a reproducible way to validate the one-dimensional timing optimum without silently ignoring the original failure. The corrected-location inherited solutions show no material improvement from finer search.

Timing modes remain relevant to local joint solutions. These profiles do not prove a global optimum between all sampled points and do not establish true timing or satellite identity. In the first scan at the corrected location, the weaker training peak actually predicts held observations better by 6.280 log units, further illustrating that stronger training likelihood alone is not a physical accuracy certificate.

The next useful test is a declared joint refit from the independently validated rank timing choices, followed by equal-budget transfer checks if that resolves the location discrepancy. Do not promote an optimizer or geographic estimator based on this exposed three-scan diagnostic alone.

No RF collection, export, production edit or reference-based selection occurred. This uses the same zero-height, site-conditioned candidate model and exposed DS8 scans as the [preceding diagnosis](../2026_09_29_ds8_union_timing/README.md). Reports remain local. `evidence.sha256` binds all report artifacts.
