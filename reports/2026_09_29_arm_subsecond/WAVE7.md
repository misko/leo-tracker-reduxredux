# Wave 7: packing, precision, and regional search

Exact histogram reuse and integer-only ranking keys reduce the matched small
ARM panel from **863.029 to 831.795 ms per 120 ms dual-RX dwell** (3.62%).
All 182 emitted candidates are identical and **119/119 standard individual
hits** remain. On the separate mixed-rate host704 panel, all 86,439 candidate
objects are identical, recovering **19,217/19,581 standard hits** unchanged.
These results are non-PGO; independent savings cannot be added to PGO gains.

The exact combination has now also been measured with ARM-trained PGO on the
same disjoint held-out 32 dwells used for Wave6 PGO:

| Method, same held-out panel | ARM CPU ms/dwell | Standard hits recovered |
|---|---:|---:|
| Wave5 control | 917.633 | 904/921 |
| Wave6 exact combination with PGO | 776.473 | 904/921 |
| Wave7 exact histogram/key changes with PGO | **758.592** | **904/921** |
| Approximate proposal8/half-grid/tracking/radius1 with PGO | **473.795** | **854/921** |

Wave7 saves a further 2.30% versus Wave6 PGO, and 17.33% versus Wave5 on
these recordings. All 1,201 candidate objects remain identical across all
704 receiver/windows. The four training dwells are excluded from evaluation;
11 component suites pass on physical ARM. This combination has not received
the larger 152-dwell ARM qualification. The training profiles, build commands,
receipts and held-out evidence are in `arm_wave7_hist_pgo`.

The approximate PGO variant reduces runtime by **48.37%** versus that same
Wave5 control and recovers **92.73% of standard hits**, versus 98.15% for
the control. It emits 1,116 candidates across all 704 windows. Its 11 ARM
component suites pass and its five training profiles are archived in
`arm_wave7_frontier_pgo`. It is a quality tradeoff, not an exact optimization;
it has not received 152-dwell ARM or DS8/DS9 qualification. This remains above
the 120 ms real-time budget and below the requested 50% runtime reduction.

The table uses the same four saved 2.5 MS/s ARM dwells and 88 overlapping
20 ms receiver/windows. Every approach processes all windows. The last column
is a separate scientific check on 704 mixed-rate DS7 dwells (15,488 windows),
not an ARM timing result. These panels are subsets, not all DS7.

| Method | ARM CPU ms/dwell | ARM standard hits recovered / 119 | Host704 standard hits recovered / 19,581 |
|---|---:|---:|---:|
| Wave6 exact control | 863.029 | 119 | 19,217 |
| Single histogram scan | 840.302 | 119 | 19,217 |
| Above plus integer keys | **831.795** | **119** | **19,217** |
| Whole FP32 final scorer v2 | 856.661 | 119 | 19,217 |
| Above plus Winograd coarse kernel | 974.935 | 119 | 19,217 |
| Winograd integration v2 | 1,004.374 | 119 | 19,217 |
| Eight proposal frames | 786.619 | 116 | 18,983 |
| Neighbor proposal reuse, minimum two matches | 738.493 | 119 | 19,208 |
| Neighbor proposal reuse, minimum one match | 695.306 | 119 | 19,205 |
| Radius one plus exact rank improvements | 776.227 | 119 | 19,206 |
| Eight proposal frames, half proposal grid, coarse8 | 736.500 | 102 | 17,924 |
| Above plus neighbor reuse | 672.657 | 102 | 17,939 |
| Eight proposal frames, half grid, neighbor reuse, full coarse16 | **578.726** | **116** | **18,805** |
| Above with narrower radius-one search | 506.355 | 108 | 18,465 |

`collect_wave7.py` checks completed manifests, row hashes, receipt hashes and
audit bindings; `wave7-results.json` contains the underlying measurements.
Timing includes proposals and complete dwell input preparation. Initial
workspace setup, file I/O, JSON output, and radio capture are excluded.
Single-core CPU time does not establish simultaneous-capture performance.

Additional compiler choices were physically measured against the exact
831.795 ms histogram/key control on ARM4:

| Code-generation change | ARM CPU ms/dwell | Standard hits recovered |
|---|---:|---:|
| Thumb-2 encoding, `-O3` | 834.190 | 119/119 |
| ARM encoding, `-O2` | 900.058 | 119/119 |
| Safe proposal-buffer `restrict` annotations | 832.480 | 119/119 |

All 182 candidate objects remain identical. Each build passes ten component
suites on physical ARM. Thumb and alias annotations show no useful gain;
`-O2` regresses. These remain excluded from the preferred combination.

The exact ranking optimization counts all radix digits in one scan, because
permuting the input cannot change digit counts. It also replaces a floating
point zero comparison with equivalent integer bit handling. This saves memory
passes and instructions without changing scientific arithmetic. Owned tests
cover signed zero, subnormals, ties, arbitrary finite floats and all FFT sizes;
host, sanitizer and physical ARM component checks pass.

Whole FP32 scoring preserves recovered hit identities on host704, but changes
scores and is therefore approximate. Its 0.74% total ARM saving is marginal.
Its strengthened cancellation tests observe up to 0.001725 absolute score
error, although ordinary cohort score differences are much smaller. Lower
precision alone is not a guarantee of useful speedup.

Reducing coarse frames to eight makes candidate selection less selective.
The aggressive ARM variant emits 332 candidates versus 182 for the control:
the extra refinement and scoring erase much of the early-stage saving. It
also loses standard hits. The seemingly good 90.22% recovery on the larger
2.5 MS/s host panel does not override 102/119 recovery on the small ARM panel.

Restoring all 16 coarse frames in that last combination improves both speed
and recovery: **578.726 ms/dwell and 116/119 hits** on ARM4, with only 170
emitted candidates. Host704 recovers 18,805/19,581, including 4,442/4,573
(97.14%) at 2.5 MS/s. This is 39.74% less CPU than the matched Wave5 ARM4
control (960.455 ms), but remains an approximate tradeoff and is not yet
qualified on the larger ARM panel. Fewer operations in an early stage can
make the complete pipeline slower when they increase downstream work.

Narrowing that combination to radius one reaches 506.355 ms on ARM4, with
108/119 hits (90.76%). Host704 retains 18,465/19,581, including 4,235/4,573
at 2.5 MS/s (92.61%). This is 47.28% less CPU than Wave5 ARM4, with additional
quality loss. It is not a current-quality-preserving 50% result.

Exact rank certification was also tested. Linear histogram bins certify the
correct top candidates for 82.92% of windows, with exact sorting as fallback.
All candidate outputs remain identical, but proof construction and scans
increase host ranking time from 7.66 to 13.69 ms/dwell. It was not promoted
to ARM timing. Cross-window coarse-dot caching similarly has only 14.88%
reuse; even a zero-cost cache saves at most about 20 ms before lookup costs.

A separate Winograd F(4,3) kernel computes four adjacent epoch outputs with
half the complex multiplications per three-tap block. Its CPU0 microbenchmark
against an explicit NEON direct comparator takes 910.655 versus 1,519.452 ms
for the repeated kernel workload (40.07% less). This is **not dwell timing**;
transforms, tails, support boundaries, and full-search integration must be
measured before claiming an overall gain. Its algebraically equivalent
transform changes FP32 addition order and requires detection qualification.
The earlier scalar-direct/NEON-Winograd comparison is confounded and is not
used for this claim. Full integration on top of the FP32 final scorer is
slower: **974.935 versus 856.661 ms/dwell**, with coarse time rising to
257.884 ms. It retains 119/119 ARM hits and the host704 aggregate count, but
the first integration is rejected for speed. Reducing multiplies in a small
kernel does not establish lower full-pipeline cost.

One bounded integration revision restores vector magnitudes and attempts to
keep epoch accumulators in registers. It still regresses to **1,004.374 ms**,
with **287.539 ms** in coarse search. Both ARM variants pass the owned
all-rate coarse numerical checks and retain 119/119 hits; host704 identity
audits also show no lost/gained recovered hits. Neither implementation is
adopted. The standalone operation-count reduction is real, but the complete
implementation's additional transforms, accumulation and data handling cost
more on this processor.

The 50% overall ARM runtime-reduction goal remains open. The preferred exact
changes preserve the existing detector's recovered hits; they do not recover
every hit from standard analysis. Approximate shortcuts stay separately
identified and are not silently substituted into the preferred detector.
