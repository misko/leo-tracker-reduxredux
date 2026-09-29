# First/last-window GLRT interpolation: measured prototype

The prototype works, but **does not meet the 90% individual-hit recovery
target**. The most permissive tested mode recovers 653/843 standard detections
(77.46%) on the 32-dwell mixed-rate DS7 development panel. ARM timings range
from 4.84 to 20.08 seconds per 120 ms dual-RX dwell, depending on the policy.
None is real time. These results do not justify replacing the existing search.

See [ARM runtime profile](RUNTIME_PROFILE.md) for the existing full-search and
restricted-search bottlenecks, and [protocol](PROTOCOL.md) for frozen policies.

## Experiment and exact recovery

All modes fully search the first and last 20 ms window of each receiver,
associate candidates, and run real current-IQ GLRT at predicted positions for
the nine middle windows. No baseline coordinates seed detection. Tracking CFO
and unwrapped timing phase are interpolated; each seed tests three integer
timings. The acquisition CFO input is clamped to its supported range, while
the actual GLRT residual determines final tracking CFO. Only the evaluation
uses standard-pipeline results: margin >=0.025, same receiver/window,
one-to-one matching within two samples and 8 kHz.

The quality cohort is **32 saved DS7 dwells, 704 receiver-specific 20 ms
windows, 843 standard positive candidate entries**, covering both edges and
2.5/5/7.5/10 MS/s. It is not full DS7 or the previous 704-dwell cohort.

| Policy | Standard hits recovered | Recovery | Unmatched new positive entries | Windows with actual GLRT calls | Actual GLRT calls |
|---|---:|---:|---:|---:|---:|
| Interpolate paired endpoints only | 474/843 | 56.23% | 45 | 326/704 | 2,277 |
| Also propagate unmatched endpoint candidates | 601/843 | 71.29% | 283 | 704/704 | 27,549 |
| Above, plus blind fallback when no local positive exists | 653/843 | 77.46% | 283 | 704/704 | 30,203 |

All modes represent all 704 windows in output; pairs-only actually skips GLRT
in 378 middle windows with no paired seed. Each mode runs 128 endpoint full
searches. Union executes local searches in all 576 middle windows; fallback
adds 323 full searches, for 451 full-search windows total. Extra positives are
not evidence of recovered original hits, nor automatically truth false alarms.

| Rate | Dwells / windows | Original hits | Pairs recovered | Union recovered | Union + fallback recovered |
|---|---:|---:|---:|---:|---:|
| 2.5 MS/s | 8 / 176 | 205 | 109 (53.17%) | 139 (67.80%) | 157 (76.59%) |
| 5 MS/s | 8 / 176 | 152 | 68 (44.74%) | 96 (63.16%) | 118 (77.63%) |
| 7.5 MS/s | 8 / 176 | 258 | 174 (67.44%) | 203 (78.68%) | 207 (80.23%) |
| 10 MS/s | 8 / 176 | 228 | 123 (53.95%) | 163 (71.49%) | 171 (75.00%) |

## Physical ARM runtime and quality

Measured serially on PLUTO+ .15 CPU0 using four saved 2.5 MS/s dual-RX dwells
already used for earlier ARM comparisons. There are 88 windows and 119 standard
positive entries. Input is in RAM during processing. No RF or simultaneous
capture; no claim of sustained real-time operation. Timings include sample
preparation, endpoint discovery, association, local GLRT and any fallback, but
exclude file transfer/read and initial workspace/template setup.

| Policy | CPU seconds/dwell | Standard hits recovered on ARM | Unmatched positives | Windows actually scored | Actual GLRT calls |
|---|---:|---:|---:|---:|---:|
| Paired endpoints | 4.837 | 52/119 (43.70%) | 5 | 52/88 | 272 |
| Endpoint union | 10.159 | 72/119 (60.50%) | 31 | 88/88 | 3,458 |
| Union + fallback | 20.084 | 83/119 (69.75%) | 31 | 88/88 | 3,757 |

The historical boundary-fallback full search costs 25.085 seconds on these
same four dwells and recovers 119/119. Nominal speedups are 5.19x, 2.47x and
1.25x, respectively, with substantial detection loss. This is a separate
historical reference measurement, not interleaved A/B timing. The 32-dwell
quality panel and four-dwell timing subset must not share denominators.

| ARM stage, seconds/dwell | Pairs | Union | Union + fallback |
|---|---:|---:|---:|
| Input preparation | 0.053 | 0.053 | 0.052 |
| Four full endpoint searches | 4.554 | 4.558 | 4.554 |
| Association + interpolation | 0.000215 | 0.000447 | 0.000432 |
| Middle-window local GLRT | 0.229 | 5.547 | 5.368 |
| Middle-window full-search fallback | 0 | 0 | 10.109 |
| **Total** | **4.837** | **10.159** | **20.084** |

Four endpoint searches alone cost about 4.55 seconds, 38 times the entire
120 ms real-time allowance. Union propagates 11–16 seeds per middle window
on the host panel and tests three timings each. Fewer blind searches therefore
does not necessarily mean fewer final GLRT calls. The direct-CI16 optimized
scorer is not integrated into this prototype.

## Why it loses detections

An independent audit verifies all 128 endpoint windows and 1,024 endpoint
candidate objects exactly match the frozen boundary search for all three
modes, including timing, acquired/tracking CFO, exact/control score and margin.
The loss arises in middle-window processing, not altered anchors.

Of 64 receiver-dwells, 42 have no admissible endpoint pair. In pairs-only,
91 original middle hits have no paired seed; another 278 are missed despite
local searches. Union removes empty seed inventories and gains 127 hits,
but still misses 242 middle hits. Endpoint support, association, prediction
precision and margin decisions can all contribute; this experiment does not
identify a physical track for every retained candidate.

The fallback mode recovers all 52 standard positives in its fallback windows,
but leaves 190 middle hits unrecovered in windows that already have some local
positive. **One detected candidate is not evidence that the other original
candidate detections in that window were conserved.**

See `endpoint-anchor-audit.json` and [association diagnostic](PAIR_SCARCITY.md).
The timing gate rejects many CFO-compatible combinations; simply widening it
risks associating different signals or aliases. It is not an established fix.

## Conclusion and follow-up priorities

Do not expand this unchanged policy to the 704-dwell cohort: all variants
already fail the quality target on the development panel. Keep these failures
as regression evidence. A useful next prototype would use endpoint CFO banks
to guide a **fresh middle-window timing acquisition**, instead of assuming that
endpoint timing predicts each retained middle candidate. Pairing should retain
alias alternatives and current-window evidence; refresh decisions must account
for missing individual hypotheses, not merely absence of any hit. Any such
variant still needs the cheaper lag-based acquisition and optimized final
scorer to reduce the measured endpoint/local-scoring costs. These are proposed
experiments, not measured improvements.

## Validation and reproducibility

SOL implemented the C prototype; Terra independently audited standard-hit
recovery and endpoint equality. Host, ASAN/UBSAN and ARM component tests pass;
four Python scorer tests pass. Tests cover all rates, phase wrapping, window
translation, deterministic association, aliases, empty endpoint inventories
and output contracts. A window-coordinate bug was fixed before data runs.
All reported runs use v2, with hash-bound source/binary/input/template receipts.

Run `run.py --help` and `score.py --help` for the preserved drivers. Modes are
`pairs-only`, `union`, `union-fallback`; `--arm` selects the four-dwell hardware
cohort. See README for binary invocation at any supported rate. `profile.py`
reconstructs the runtime tables, excluding nested timers from stage sums.

Publication includes source, build receipts, cohort manifests, scores, audits
and a single selected source snapshot. Large raw outputs, IQ and compiled
binaries remain in the development workspace with hashes recorded in receipts.
This is a research prototype, not a change to the deployed analysis pipeline.
