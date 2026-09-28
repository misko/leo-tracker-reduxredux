# Frozen GLRT fallback validation on DS8 and DS9

The unchanged boundary-fallback method recovered **19,496/19,499 original
individual GLRT hits (99.9846%)** on 680 new dwells across all 170 DS8/DS9
recordings. At the priority rate of 2.5 MS/s it recovered **4,550/4,550**.
Separate single-core PLUTO+ checks recovered **189/189** original hits and
measured **1.34x speedup on DS8 and 1.32x on DS9** versus the latest exact-cache
baseline. No retuning or algorithm change was made for this validation.

## Original hits and windows

Four metadata-selected chronological quartile-midpoint visits were processed
per recording. Each saved 120 ms dual-RX dwell supplies 22 overlapping 20 ms
windows (10 ms stride). All eight candidate entries in every window remain.

| Dataset | Recordings | Dwells | 20 ms windows evaluated | Original individual hits | Recovered original hits | Recovery | Original positive windows recovered |
|---|---:|---:|---:|---:|---:|---:|---:|
| DS8 | 65 | 260 | 5,720 | 7,282 | 7,281 | 99.9863% | 2,753/2,753 |
| DS9 | 105 | 420 | 9,240 | 12,217 | 12,215 | 99.9836% | 4,371/4,373 |
| Total | 170 | 680 | 14,960 | 19,499 | 19,496 | 99.9846% | 7,124/7,126 |

| Dataset | Rate (MS/s) | Windows evaluated | Original hits | Recovered hits |
|---|---:|---:|---:|---:|
| DS8 | 2.5 | 1,760 | 1,901 | 1,901 |
| DS8 | 5 | 1,496 | 1,888 | 1,887 |
| DS8 | 7.5 | 1,320 | 1,983 | 1,983 |
| DS8 | 10 | 1,144 | 1,510 | 1,510 |
| DS9 | 2.5 | 1,760 | 2,649 | 2,649 |
| DS9 | 5 | 1,056 | 1,316 | 1,316 |
| DS9 | 7.5 | 1,760 | 1,937 | 1,937 |
| DS9 | 10 | 4,664 | 6,315 | 6,313 |

Every recording has a positive reference denominator. All 170 exceed 99%
recovery: 167 recover every original hit and three lose one hit each. The
worst recording retains 127/128 (99.21875%); the others retain 131/132 and
141/142. No recording falls below the requested 90% target.

The result contains 19,498 positive hypotheses: 19,496 matched original hits
plus two unmatched new positives. Each new positive appears in an originally
negative window (one DS8 7.5 MS/s, one DS9 5 MS/s). They are not assumed to be
true or false detections without independent signal ground truth. Thus the
equal total count of 7,126 native and original positive windows does not mean
every original positive window was recovered.

The three losses are nonfallback near-threshold crossings: original margins
0.025123086, 0.025691169 and 0.025097966 become 0.024786939, 0.024589497 and
0.024734416. Their timing/frequency still meets the matching gate, but their
new margins fail 0.025. All are on lower-edge dwells. Full cases, including the
two upward threshold crossings, are in `threshold-crossings.json`.

There are 119,680 candidate entries and 9,208 conditioned fallbacks (7.69%).
Including the second evaluation on those candidates gives **128,888 actual
GLRT kernel calls**. No windows or candidates were pruned.

## ARM results

Each row below uses four distinct metadata-selected 2.5 MS/s dwells, 88 windows
and 704 candidates. Both methods process exactly the same bytes on CPU0 of
PLUTO+ 192.168.1.15, reading saved IQ into RAM before timed analysis. Transfer
and setup are outside timing. Methods run serially; no RF collection or
simultaneous capture was performed.

| Dataset | Exact-cache CPU s/dwell | Frozen fallback CPU s/dwell | Speedup | Hits recovered | Positive windows recovered |
|---|---:|---:|---:|---:|---:|
| DS8 | 33.316097 | 24.785112 | 1.34420x | 53/53 | 37/37 |
| DS9 | 32.987558 | 24.956039 | 1.32183x | 136/136 | 54/54 |

Neither ARM fallback run produces unmatched new hits. The exact-cache runs
also match all original candidate fields within the established numerical
tolerances. Fallback output on ARM and host agrees for all 1,408 selected
candidate entries, including epochs and fallback decisions; maximum tracking
CFO difference is 5.83e-11 Hz and score/margin difference is below 2.02e-16.
The separate eight-dwell original baseline agrees exactly with the same
results in the large replay. Evidence is in `arm-comparison.json`,
`arm-host-parity.json` and `arm-baseline-parity.json`.

These eight dwells support transfer of the previously measured speedup to
new recordings, not a precise fleet-wide runtime distribution. Higher-rate
recovery was checked on the host; no new higher-rate ARM timing claim is made.
The approximately 25 CPU seconds per 120 ms dual-RX dwell remains far above
the 72 ms budget for continuous processing with 40% headroom.

## Integrity and limits

`PROTOCOL.md`, `plan.json` and `arm-selection.json` record the fixed method and
metadata-only selection. DS7, DS8 and DS9 source sessions and source manifest
digests are disjoint. All DS8/DS9 source manifest bindings and selected IQ
payloads were checked through the public read-only storage reader. The
original replay completed all 680 dwells with zero failures and unchanged
sources; all eight tracked source hashes equal the earlier DS7 baseline.

The frozen maximum-cardinality one-to-one matcher requires a positive margin
>=0.025, the same receiver/window, epoch distance <=2 samples and tracking
CFO distance <=8 kHz. These are individual candidate hits, not unique physical
transmitters, recording confirmations, or exact equality of all GLRT fields.
Candidate order and uncomputed verification fields intentionally differ from
the original; the inherited ordered-equality flag is not the recovery gate.

The strict scorer accepted all 680 dwells and 14,960 windows. SOL independently
confirmed the numerical totals, dataset/rate splits, affected recordings and
baseline source hashes. Terra supplied the owned runner and dataset-summary
checks. Eight harness tests pass, and the unchanged all-rate unit passes on
ARM. `EXECUTION.md` records the initial unit-timeout attempt and successful
rerun; no failed measured dwells were discarded.

This is transfer validation on later recordings at the same site. It covers
all recording identities but only 680/376,550 visits (0.181%) in the two frozen
datasets. It is not exhaustive DS8/DS9, cross-site validation, independently
labelled detection truth, or a concurrent radio-capture benchmark. DS9's
analysis-complete membership is itself an admission selection. The fixed
1000 Hz threshold remains unchanged; this experiment is not used to retune it.

Reproduction and machine-readable evidence: `EXECUTION.md`, `host-hit-audit.json`,
`host-summary.json`, `baseline-v1/run.json`, and the per-method ARM folders.
