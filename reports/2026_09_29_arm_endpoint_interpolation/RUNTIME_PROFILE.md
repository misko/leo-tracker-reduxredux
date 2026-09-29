# ARM runtime of one 120 ms dual-receiver dwell

The dwell is **120 milliseconds**, with 300,000 samples per receiver at
2.5 MS/s. Standard analysis examines eleven overlapping 20 ms windows per
receiver (10 ms stride): 22 receiver-windows and up to 176 retained candidate
scores per dwell. GLRT retries and local timing probes add actual kernel calls.

These profiles use instrumented process CPU time on PLUTO+ 192.168.1.15,
CPU0, on four saved DS7 dwells. No RF or simultaneous capture ran. They are
averages, not worst-case latency or sustained pipeline throughput. Existing
full-search profiles are retained measurements; endpoint profiles are newly
measured for this experiment. All compare detections with standard analysis.

| Work per dwell | Exact refinement reuse | Near-baseline boundary fallback | Restricted search + lazy FFT + FP32 proposals |
|---|---:|---:|---:|
| Timing proposals | — | — | 0.852 s |
| Coarse timing/frequency search | 19.745 s | 19.771 s | 0.414 s |
| Fine-frequency FFT search | 3.835 s | 3.839 s | 2.841 s |
| Conditioned frequency refinement | 7.384 s | 0.593 s | 1.447 s |
| Acquisition verification | 1.391 s | skipped | skipped |
| Final GLRT kernels, including retries | 0.452 s | 0.520 s | 0.577 s |
| Remaining measured search overhead | 0.360 s | 0.362 s | 0.182 s |
| **Total** | **33.167 s** | **25.085 s** | **6.313 s** |
| Standard hits recovered, 704-dwell mixed-rate development cohort | 19,581/19,581 | 19,576/19,581 | 19,400/19,581 |

The third column is a **sum of separately measured proposal and search stages**,
not a measured fused capture pipeline. Its search timing averages two runs of
the same four dwells. It also returns 18,328 unmatched positive entries on the
704-dwell quality cohort; high recovery is not equal output quality. Each
method recovers 119/119 standard hits in its small ARM timing cohort, which
does not override the larger-cohort differences above.

The table deliberately excludes the parent `acquisition` timer from the sum:
fine FFT is nested within it, and in exact mode conditioned refinement and
verification are nested too. For boundary and restricted modes conditioned
fallback occurs later. `other` is total minus the disjoint stages, so allocation,
peak selection and uninstrumented search bookkeeping are not lost. File reads,
transfer, workspace/template setup and capture are outside these search timers.

The near-baseline search spends about **79% on coarse search, 15% on fine FFT,
2% on conditioned refinement and 2% on final GLRT**. The newer restricted
method shifts the bottleneck: roughly **45% fine FFT, 23% conditioned
refinement, 14% proposal construction, 9% GLRT, 7% coarse search and 3% other**
(rounding may exceed 100%).

For real time, each 120 ms dwell must cost at most **120 ms of CPU** on one
analysis core, or **72 ms** for 40% headroom. The 6.313-second method remains
52.6 times the real-time budget and 87.7 times the headroom target. Optimizing
only the final score cannot close that gap; prediction must reliably remove
search work and reduce the number of hypotheses actually evaluated.

## New first/last-window prototype

Endpoint interpolation arithmetic is cheap; the endpoint searches and all the
local current-IQ GLRT calls are not. See [experiment results](REPORT.md) for
all three modes and their exact recovered-hit counts. `runtime-profile.json`
contains complete measured endpoint stage costs and source hashes, generated
by `profile.py`. Unlike older search timers, endpoint totals explicitly include
per-window CI16 preparation and association, but still exclude file I/O and
initial workspace setup.

This prototype currently uses the frozen boundary-fallback scorer, not the
separate direct-CI16 scoring optimization. The latter's 274 ms for all 176
supplied-coordinate scores is a different benchmark, not its runtime here.
