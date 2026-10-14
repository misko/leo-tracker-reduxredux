# Receiver-time qualification stopped at interpolation knots

The initial timing-profile version failed before any profile completed: each case consumed one source objective replay and zero fits, then rejected a prediction central finite difference exceeding the fixed.001Hz/s gate. Both failed namespaces and frozen sources are preserved. The authorized postmortem measured **interpolation-cell crossings**, not a gross native derivative failure.

| Case/step | Entries | Crossed cells | Central max error Hz/s | Stable-cell max | Source-cell one-sided max |
|---|---:|---:|---:|---:|---:|
| 053/1e-4s | 95370 | 73 | .140733797 | .000003535 | .004365473 |
| 053/1e-5s | 95370 | 7 | .105297358 | .000035912 | .000468534 |
| 059/1e-4s | 143754 | 127 | .159591485 | .000003519 | .004594787 |
| 059/1e-5s | 143754 | 20 | .134196367 | .000036173 | .000489660 |

There were zero visibility changes and every entry had an available same-source-cell one-sided difference. Maximum central discrepancies occur where minus/zero/plus queries occupy different interpolation cells. For example053's largest1e-4 error queried201.000019s across a node at201s, and059 queried36.500008s across36.5s. The original kernel differentiates the actual source cell; a central difference across the knot mixes two tangents. Reducing the step decreases smooth one-sided truncation error but cannot make a crossed-cell central average equal the source tangent. The pure component's synthetic kink regression reproduces this distinction while a deliberately wrong derivative inside a stable cell remains wrong.

The postmortem completed05311.956s/05914.996s,5 explicit orbital predictions each,0 objectives,0 likelihoods and0 fits, separate120/135/140-second bounds and two workers. It used only the original failed first incumbent state and retained all scientific authority. Source5b8605d24;5 tests/Ruff passed. Runtime `model-b-time-fd-postmortem-v1` under private bulk2026_10_14; terminals053`008d0400e45b48508ba85df4f0fca33e9d2d578f4637dabe79a9a685efdf9411` and059`707359897cfcae8081de7d20f5c1a0fc1813dc326cb45b4f27def9f0b9c44533`.

The root-reviewed corrected version will use1e-5s, retain the **original.001Hz/s gate** on stable central and source-cell one-sided predictions, and explicitly record crossed-cell central discrepancies. Its central NLL difference will be checked against the actual central prediction tangent, with source tangent and visibility changes separately reported. All grids, source states, bounds and zero-fit policy remain unchanged. This is a fresh qualification version, not a retry of the failed namespace or a loosened tolerance. No timestamp correction, geography fit or scientific accuracy claim follows from this postmortem.
