# Seconds needed on the enrolled full-length recordings

All of the first four and all of the first sixteen recordings in the frozen DS30 timing roster contain **6,770–6,773 issued windows**. Neither roster contains the 808-window DS30-0016 development fix or the 18-window DS30-0227 withdrawal. Those cases reveal fixed costs and correctness failures cheaply. A shortcut applying only to recordings that short has zero direct weight in the two longer panels. [Signed roster sizes, acquisition and publication clocks](measurements/acquisition-throughput.json) · [Prior selection and timing model](solver-transfer-budget.md)

We priced a change that saves the same number of seconds on every full-length recording with a split timing measurement. The model uses the dense candidate's measured **252.51 compressed MB/s at zero exposed wait**, each scan's own byte count, and the previously frozen three-size solver interpolation with exact dense graph reuse. It carries forward the original approach to publication, common cost and unsplit failure. DS30-0022, which failed in installed v3, remains charged its full **110.77 s** in the sixteen-case panel. Recovered v3 failures have separate scientific outcomes. None of the projected timings below is a fresh paired run. [Model inputs](measurements/solver-transfer-budget.json) · [Case-level results](measurements/roster-savings.json) · [Calculation](roster_savings.py)

| Original roster | Modeled median / summed ratio at zero acquisition wait | Uniform net seconds needed per adjustable recording for median gate | Uniform net seconds needed per adjustable recording for summed gate | Needed for both |
|---|---:|---:|---:|---:|
| First 4 | 0.545 / 0.525 | 4.616 s | 2.472 s | **4.616 s** |
| First 16, one charge held fixed | 0.514 / 0.524 | 1.504 s | 2.735 s | **2.735 s** |

The candidate time on each completed row is the sum of acquisition CPU estimated from original compressed size, interpolated numerical work, common charge and the original terminal-to-exit tail. We apply a uniform reduction to those rows, recompute each ratio and reorder them for the median at each trial amount. The summed gate uses total elapsed time. If an additional **5.0 s of exposed input wait** occurs per adjustable recording, the first-four saving requirement grows to **9.616 s** and the first-sixteen requirement to **7.735 s**, with every other assumption fixed. The earlier dense raw run actually showed 28.046 s between acquisition elapsed and CPU. That is a single observation under a different storage state. [Original dense split](dense-ingress-attribution.md)

| First four, in enrollment order | Issued windows | Historical installed v3 elapsed | Modeled candidate with zero acquisition wait | Candidate excess over half the original |
|---|---:|---:|---:|---:|
| DS30-0374 | 6,770 | 84.85 s | 50.30 s | +7.9 s |
| DS30-0008 | 6,772 | 113.02 s | 59.36 s | +2.8 s |
| DS30-0155 | 6,773 | 111.68 s | 48.92 s | −6.9 s |
| DS30-0001 | 6,773 | 93.80 s | 52.99 s | +6.1 s |

The similar recording lengths hide substantial differences in the original receiver, solver and storage clocks. A universal **0.7 s** saving would move first-four median/summed ratios to **0.538/0.518**, and first-sixteen to **0.508/0.518**. On dense DS30-0008 the 4.616 s design point is about **14%** of its 32.403 s acquisition CPU, or **0.390 ms for each of its 11,834 short calls** if only those calls change. The weak 44 ms phase-forecast gain has a place in a combined build. The main timing opportunity is still several seconds on a roughly 6,770-window input. A cheap way to test transfer is to replay a complete saved solver outcome on a differently sized physical fix, then a full-length case that exercises a different balance of solving and acquisition. A larger raw pair requires a single low-priority slot and comparable storage conditions. [Dense receiver call census](quiet-cycle.md) · [Weak forecast](exact-phase-forecast.md) · [Prior weak and medium transfer](prospective-0316-solver.md)
