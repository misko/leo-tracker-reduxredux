# B059 half-function calibration compatibility

The unchanged full calibration basis cannot exactly represent the two fitted half correction functions on their observed rows. The best unconstrained projection leaves **113.886101Hz RMS**, max499.692906Hz. Its coefficients are already inside the original legal boxes, and the bounded projection is identical. This is not a bound or rank-deficiency artifact. It is meaningful relative to sigma125Hz but does not establish hardware error: the half functions were fitted with different geography, orbital timing and q, whose effects can be absorbed into calibration.

Source/protocol `bbd0aa3e4` passed three owned tests and Ruff before freeze. The bounded audit completed in14.989s including source checks/preparation, with exactly three original calibration-function evaluations and two explicitly disclosed numerical least-squares projection procedures. It used zero probability objectives, orbital predictors and localization optimizer calls. Original held/locked observations, references and QNAP were untouched.

The functions were evaluated at the SAME actual full timestamps/RFs/receiver/group labels. Low values were spliced onCH1–4 and high onCH5–8, the unchanged full baseline subtracted, and the result projected into the original five affine/RF columns,18 common-clock coefficients and two group offsets. Each source function independently replays its own original coefficient design within4.366e-11Hz; no half-frame coefficient reinterpretation or projected localization seed was introduced.

The2522×25 matrix has rank25 both before and after the original fitter's column scaling. Scaled condition1761.425544; unscaled3446.617174. The full singular arrays/tolerances and coefficients/bounds are retained. The unconstrained minimum-norm solution has no legal-bound violations. Box-constrained BVLS reports the same unconstrained optimum, status3, zero iterative steps, with identical residuals; its reported optimality diagnostic is.002763 in scaled linear-projection units, not the localization KKT statistic.

| Measured rows | Count | Projection RMS Hz | Max absolute Hz |
|---|---:|---:|---:|
| all |2522 |113.886101 |499.692906 |
| low |1550 |82.087443 |164.287779 |
| high |972 |151.351970 |499.692906 |
| RX0 low |1110 |75.125486 |164.287779 |
| RX0 high |710 |142.113064 |499.692906 |
| RX1 low |440 |97.465366 |162.427147 |
| RX1 high |262 |173.939136 |392.632466 |

Receiver-wide means and receiver×band means are effectively zero after projection. Time structure remains:20-second-bin RMS values span25.340Hz (bin8) to232.768Hz (bin0); other early bins1/2 are132.200/125.945Hz and final bin14 is130.451Hz. These are differences between fitted correction functions, not measured CFO residual noise estimates. The current full correction minus the unprojected splice has138.181293Hz RMS and561.296484Hz maximum.

The projected RF coefficient is−510.069707, receiver slopes3.636582/−.744052Hz/s, group offsets−21124.198220/+39739.927974Hz and clock coefficients within−145.237475..356.969141Hz, all legal. Per-half group offsets were near zero because they are confounded with per-receiver intercepts within a single observed group; the spliced projection recovers large between-group offsets. Representing those constant offsets still leaves113.886Hz residual, so the collapse alone does not account for all fitted-function incompatibility.

This supports inspecting calibration compatibility before adding band-specific satellite weights. It does not distinguish true receiver frequency behavior from geography/timing/association effects or justify dropping/downweighting a band. The approved next control fixes BOTH matched-half training XY positions, initializing every non-geographic/q parameter from CURRENTFULL rather than collapsed half states, and permits only accepted full-target profiles to release in the original disk. No projection coefficients are used as seeds.

Output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-calibration-compatibility-059-v1`. Terminal SHA256 `31674a4bb6f74d39150ccadb3d13b26bd1bd8177b275afd4361f55608cd5676f`; scientific seal `b0a893137c2e2befc7ad86fe310f74454f519b6bca4ad3949210a505a6417f72`. One worker, internal120/TERM135/KILL140. Two diagnostic numerical projections are explicitly separate from zero localization fits and zero probability-objective calls.
