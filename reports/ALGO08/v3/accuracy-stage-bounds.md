# How much can faster receiver calls buy while retaining ALGO08v3 accuracy?

On the first 64 original DS30 recordings, even **free short receiver calls plus a free position solver** reach at most **1.973× summed speedup** if the two builds keep their measured positions and must match ALGO08v3’s fix count and entire error distribution. This gives a chooser the correct build in advance for every recording, with zero selection cost. The fastest eligible combination still exceeds the 2× budget by **43.38 seconds**. The same two hypothetical changes clear 2× under the narrower requirement of matching fix counts and the counts within 1 and 2 km. Both comparisons apply the requirements independently at fixed-zero and fitted calibration. [Measured positions and clocks](ds30-routing-first64.md) · [Integer certificates and recording selections](measurements/accuracy-stage-bounds.json.gz)

| Change to the candidate, with installed time held fixed | Best summed speedup, preserve 1 and 2 km coverage | Best summed speedup, preserve every observed threshold |
|---|---:|---:|
| Measured builds | 1.505× | 1.408× |
| Transfer DS30-0016’s 10.92% short-callback CPU saving fully to wall time | 1.527× | 1.424× |
| Eliminate all 8 ms callbacks | 1.757× | 1.597× |
| Eliminate both 8 and 20 ms callbacks | 1.904× | 1.702× |
| Eliminate acquisition outside those callbacks | 2.009× | 1.783× |
| Eliminate the position solver | 1.891× | 1.690× |
| Eliminate the 8 ms callbacks and the solver | 2.311× | 1.973× |
| Eliminate both callback types and the solver | 2.572× | 2.136× |
| Eliminate all acquisition | 2.796× | 2.280× |

Each row starts with the actual per-recording wall times, including publication verification when reached. Acquisition includes the native callbacks. The solver clock excludes chart production and publication verification. Every row retains the time of any operation outside the named change. The calculation keeps the candidate’s measured position and fix decision even when the operation that produced them has been priced at zero. The installed fallback retains its measured time and outcome. This makes each elimination a ceiling for that specific strategy on this panel. No executable algorithm was timed in these scenarios. [Acquisition and solver accounting](first64-producer-transfer.md) · [Short-call clocks and physical donor](short-phase-first64.md)

To satisfy **both** timing gates and preserve both full distributions by cutting only the candidate’s acquisition, a uniform **77% cut is insufficient** and a **78% cut is sufficient** in this model. Cutting the native callbacks and solver together requires between **86% and 87%** on the same integer-percentage grid. At only the 1 and 2 km thresholds, the corresponding crossings are 53–54% and 59–60%. For each lower endpoint the certificate rules out even the summed gate. At each upper endpoint a single admissible choice of builds also passes the median gate.

The useful next targets are changes that recover accurate fixes at low cost, or changes that also reduce the cost of the installed-quality path. Optimizing just the mixed receiver’s 8 ms verifier leaves most of the measured accuracy-constrained deficit. All 64 observations came from one roof. [Reproducer](accuracy_stage_bounds.py)

## How much faster would the accurate fallback have to be?

Keep the same two sets of positions and allow the chooser to use an accelerated version of ALGO08v3 wherever needed. All speedups still use the original measured ALGO08v3 time on each recording as the denominator. The table grants the mixed path the stated savings and gives the fallback a uniform reduction in its entire wall time. The buffer estimate comes from the DS30-0049 reuse-first donor, scaled by authenticated input bytes and capped at the non-native acquisition budget on each recording.

| Mixed-path assumption | Recordings finishing within half time on mixed alone | Maximum of those compatible with both full error curves | First whole-percent cut in fallback time sufficient for the summed gate |
|---|---:|---:|---:|
| Measured candidate | 10 | 9 | 50% |
| Measured DS30-0016 short-kernel percentage and projected input-buffer savings | 12 | 11 | 50% |
| Hypothetical 1.5× native callbacks, 1.4× solver and projected input-buffer savings | 43 | 31 | 43% |

In the most favorable row, the summed gate can pass after a 43% fallback reduction. The **median still requires the fallback itself to be twice as fast**. At any smaller uniform reduction, every fallback choice takes longer than half of its original time. The count certificate proves at most 31 of 64 recordings can finish within half time while retaining the observed accuracy distribution. Consequently, both middle observations take longer than half time. At exactly 50% the certificate includes a feasible assignment that clears both timing gates. The same argument holds for the other two rows. This requirement applies to the specified outputs and uniform fallback acceleration. Improving the mixed path’s positions, usefully changing which individual recordings receive the largest savings, or directly producing v3-quality fixes with a different method changes the calculation. [Input donor](first64-producer-transfer.md) · [Installed detector cost on the same 64 cases](installed-science-first64.md)

The limit changes with the recordings under evaluation. Using the established first-30 development boundary, free short callbacks plus a free solver give a maximum **1.580×** on the first 30 and **2.183×** on the next 34. Only the latter assignment meets both gates. Under the 1.5× native and 1.4× solver assumption with buffer savings, at most **12 of 30** and **18 of 34** half-time candidates can be selected while preserving each subset’s own full curves. The pooled result uses the coverage of all 64 together and allows a gain in one subset to offset a loss in the other.
