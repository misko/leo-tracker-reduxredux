# Native detection and tracking: development tradeoffs

The new experiment permits measured quality tradeoffs, as requested by the user.
It preserves the earlier experiments and their failed gates. The frozen protocol
is `EVAL_DESIGN.md`; immutable per-stage source locks and complete JSON receipts
record the exact detector, application comparator, tests, inputs and outputs.

The native detector is a different, smaller decision detector, not the full
scanner rewritten with identical output. It uses the existing TG11 native C /
FP32 FFTW engine, one blind proposal per probe, interference conditioning and
alternating pilot symbol regions. The application searches ten candidates per
probe and uses early pilot symbols. Both inspect eleven probes per receiver in
blind mode. The tracked variant first tests two previously acquired hypotheses
on fresh samples and falls back to native blind discovery if confirmation fails.

## Constructed controls and cache stress

Stage A completed all 42 physical cases / 84 receiver cases per method. Both
native methods produced 52 truth-associated positives and 32 true negatives,
with no required-policy failures. Tracked and blind decisions agreed in activity
and associated identity on all 84 receiver cases.

The tracked route had four genuine guided successes, four guided failures with
blind fallback, and 76 cold calls. Successful dual-RX repeat confirmations took
about 0.89–0.92 ms versus 15.75–16.52 ms for blind processing. The complete
ten-step sequence improved only 1.217x (161.196 / 132.429 ms aggregate CPU).
These repeated-array controls establish mechanics, not field cache coverage.

The independent same-CFO challenge completed 14 physical steps / 28 receiver
cases per method. All 16 pilot receiver cases matched injected truth and all
12 negative receiver cases remained inactive. Tone replacements at 0 Hz,
+4 kHz, and {-50 kHz, 0, +50 kHz} each failed guided confirmation and fell back
to a blind negative, clearing state. No stale positive occurred. Alternating
negatives mean later pilots were cold; this challenge has no successful guided
hits and does not measure a cache speed benefit. It is not an estimate of rare
field false alarms or proof against every pilot-like interferer.

Stage A has no application run. Its generic reference-addition counts are not
errors; physical truth and required-policy results are the relevant metrics.

## New constructed development data

Stage B completed all 26 physical cases / 52 receiver cases. Each method ran
once on every case, including the weakest injected pilots and partial symbol
regions. All native calls were below 120 ms in both CPU and observed wall time.

| Rate | Application median CPU | Blind median CPU | Tracked median CPU | Blind aggregate speedup | Tracked aggregate speedup |
|---|---:|---:|---:|---:|---:|
| 2.5 MS/s | 1661.82 ms | 17.53 ms | 16.63 ms | 94.49x | 105.37x |
| 5 MS/s | 4222.14 ms | 36.53 ms | 35.55 ms | 115.48x | 126.60x |

Ratios use summed paired CPU, not ratios of the table's medians. Input loading,
hashing and engine initialization are excluded; CI16 conversion, confirmation,
fallback and state work are included. One P-core, numerical thread counts one,
rotated method order, and one chronological state update per case were used.

Both native modes had 38 truth-associated positive receiver cases, ten inactive
constructed negatives, and four inactive weak injected pilots. They agreed on
activity and identity in all 52 cases. There were no native positives failing
injected-pilot association. These small negative counts cannot establish a low
population false-alarm rate.

The fixed ladder brackets the native decision transition at both rates: the
-30 and -24 dB injected receiver cases were inactive, while -18, -12, -6, 0,
+6 and +12 dB were truth-associated positives. There is one realization per
level/rate, with differing CFOs, edges and noise seeds; this is not a calibrated
detection-probability curve. The -18 dB native positive margins already exceed
0.15, so the set does not sample native positives close to the 0.025 gate.
At 2.5 MS/s
the application did not retain a positive at -18 dB while native did.

Reference identity retention was 17/18 receiver positives at 2.5 MS/s and
18/19 at 5 MS/s. Both apparent losses are active but unassociated late-only
symbol-region cases: native matches injected truth, while none of the
application's retained pairs matches the injected trajectory under its own
early-symbol support contract. Thus the generic >5% reference-loss bands here
do not mean >5% physical sensitivity loss. All ten application-positive visits
per rate retained an associated result on at least one receiver. Keep receiver,
visit, reference agreement and physical truth metrics distinct.

In the two-pilot controls, native selects a valid `pilot-b`; the application
inventory contains both `pilot-a` and `pilot-b`. Detection of one valid signal
therefore does not demonstrate retention of both simultaneous signals. This is
a concrete reporting/coverage tradeoff, even when the visit decision is right.
See `AUDIT_DATASET_RESULTS.md` for the independent assessment audit.

## Recorded chronological development replay

Stage C completed all 64 saved dual-RX visits, 32 per rate, in source-time order
within each session with empty initial state. All source hashes remained stable.
These are development recordings without independent physical truth labels.

| Rate | Application median CPU | Blind median CPU | Tracked median CPU | Blind aggregate speedup | Tracked aggregate speedup |
|---|---:|---:|---:|---:|---:|
| 2.5 MS/s | 1692.44 ms | 16.75 ms | 14.77 ms | 100.06x | 131.02x |
| 5 MS/s | 4358.38 ms | 35.48 ms | 19.82 ms | 122.80x | 167.04x |

Every native call finished below 120 ms in CPU and observed wall time. Maximum
observed wall times were 20.83/43.24 ms blind and 18.76/40.84 ms tracked at
2.5/5 MS/s. These are single measurements per recording, not population tail
guarantees, and exclude initialization, loading and hashes.

| Metric | 2.5 MS/s | 5 MS/s |
|---|---:|---:|
| Application-positive visits retained with an associated pair | 24/24 | 32/32 |
| Additional native-positive visits | 2 | 0 |
| Application-positive receiver identities retained | 33/37 | 34/42 |
| Reference-positive receivers now inactive | 3 | 8 |
| Active receiver with an unassociated reference identity | 1 | 0 |
| Native-positive receiver where application was inactive | 2 | 2 |

Both native modes have these same quality counts. Across rates, all 56
reference-positive visits retain an associated detection, but only 67/79
positive receiver identities are retained. The 12 identity losses (15.19%)
include eleven inactive receiver results and one different active identity;
this is not a demonstrated small receiver-level accuracy loss. Per-rate loss
is 10.81%/19.05%, above every proposed <=5% comparison band. The active
2.5 MS/s mismatch is near the reference timing but approximately 227 kHz away
in CFO. Additional native positives remain unadjudicated real-data evidence,
not established physical false alarms. Retaining a visit through the other
receiver does not preserve dual-receiver measurement coverage.

Actual tracking adds 1.309x/1.360x aggregate CPU improvement over native blind.
There are 31 successful guided receiver calls, 31 guided failures followed by
blind fallback, and 66 cold calls across 128 receiver occurrences. Blind and
tracked agree in activity on all 128; every active tracked pair associates to
the blind pair, and both modes are inactive on the remaining rows. This is
observed agreement under the 2 us/8 kHz gates, not bit-identical full reports.
The receiver-level reference losses come from the native detector/search
architecture, with no additional loss introduced by tracking in this replay.

The practical next candidate should spend some native speed headroom on more
proposals or targeted receiver verification, then compare the resulting
receiver retention, multi-signal coverage and cost. If only one detection per
visit is required, the observed tradeoff is much more favorable, but unknown
additional detections and untested traffic still need qualification.

## Scope and remaining qualification

The constructed results support native detection as the leading compute
architecture. Guided timing is a tested prediction, not an independently fitted
new timing measurement. Cache hits cannot establish complete multi-signal
coverage, and both native modes return a smaller report than the application.

The 26 reserved validation cases remain ungenerated, and the original holdout
remains unopened. No RF was collected; no production component or deployed
scanner was changed. A development speed result does not establish production
replacement quality or end-to-end adaptive scanning latency.

Receipts: `results.controls.json`, `results.cache_challenge.json`,
`results.diagnostic.json`, and `results.real.json`. Each embeds its frozen source
lock and retains every fixed-inventory outcome, including disagreements.
The complete research component suite passed 444 tests and 11 subtests.
