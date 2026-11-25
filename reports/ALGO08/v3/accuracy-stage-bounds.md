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
