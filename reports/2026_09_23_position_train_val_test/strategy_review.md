# Strategy review: positioning below 300 m

The present evidence does not support treating a small residual, a refined grid,
or one unusually favourable block as a 300 m position result. Per-track CFO and
timing can explain a substantial part of a Doppler mismatch without locating the
receiver; orbit phase, clock and position move residuals in related directions.
The development target should therefore be a predeclared, held-out distribution
of horizontal errors, with a separate accounting of failures and ambiguity.

This review uses historical development reports and source code only. It does
not use the new cohort's outcomes to rank approaches.

## Evidence versus speculation

| Approach | Existing evidence | Decision |
|---|---|---|
| Full-catalogue, training-only association with a null component | The numerical ports and causal propagation/batching path exist. The [identity-mixture report](../2026_09_21_identity_mixture_positioning.md) documented a 5–44 candidate locally faithful support and no matched-position gain from soft identity alone. | Highest priority. It is needed to make candidate selection honest; retain candidate/timing/CFO from training and score evaluation once. Do not expect marginalization alone to remove location bias. |
| Joint location likelihood with restricted nuisance structure | The shared-position scorer and variable-projection-style per-track offset profiling exist. Original scans show prior identity disagreement and frequent timing-bound hits, so independent nuisance parameters leave serious degeneracy. | Highest priority model experiment after association. Compare a receiver-clock term, per-track CFO, and a bounded scan-level timing term one factor at a time; require information-rank and boundary diagnostics. |
| Shared orbit-rate correction | Formal orbit code has Gaussian priors, rank/condition diagnostics and exact-replay hooks. But source recurrence is required; the recent conditional study found no cross-scan recurrence under its selected identities. | Conditional priority. Run only when training support has repeated identities across independent scans. Count the prior once per source, use a predeclared bound, and reject a result lacking rank/conditioning and exact replay. |
| Correlated robust uncertainty and duration weighting | The [formal orbit model](../../src/leo/analysis/research/formal_orbit.py) implements AR(1), robust likelihood and estimated scale; [synthetic characterization](../2026_09_21_formal_position_characterization.md) degraded under unmodelled drift. | Medium priority. Tune floor, correlation and loss on training/validation predictive scores, grouped by track/scan. It can reduce over-counting but cannot establish 300 m calibration without held-out location success. |
| Soft association | A soft/null mixture port exists and exposes ambiguity, but the prior matched study had nearly degenerate posteriors and no accuracy gain. | Diagnostic/control, not primary route. Keep it as a train-only full-catalogue alternative and report entropy/null mass; do not use it to claim calibrated identity probabilities. |
| Dual-RX shared parameters or differential geometry | The [receiver-pair comparison](../2026_09_22_paired_receiver_position_comparison.md) reports a conditional sub-kilometre point but negligible common evaluation-RMS change and under-covering nominal intervals. Calibration/pointing uncertainty remains material. | Research-only until a calibration protocol is frozen. A differential delay/beam model should be introduced only with simultaneous support, measured calibration uncertainty and permutation/null controls. |

## Frozen train / validation / test design

The unit of generalization is an independent scan block, not a frequency sample,
track, or overlapping duration window. The original sixteen and the current
116-scan day inventory are already exposed development evidence. They cannot be
renamed an untouched test set. The frozen partition is 64 train, 49
retrospective-validation and 19 quarantine sessions, which supports the
48-scan validation diagnostic. There are currently zero eligible prospective
test recordings: the first candidate publication is at 15:10 after the cutoff
and the other candidates fail the frozen 120-minute embargo. Do not open
diagnostics from the quarantined or ineligible sessions to tune a model.

| Partition | Authority | Permitted work |
|---|---|---|
| Train / development seed | Original sixteen and designated retrospective blocks from the exposed inventory | Candidate support size, likelihood family, nuisance bounds, robust/correlation settings, duration weights and model implementation. |
| Retrospective validation | Whole chronological 16-scan blocks from the exposed day-116 inventory, disjoint from the particular development fit | Select one complete specification from predictive score, stability and failure rates. It remains retrospective development evidence. |
| Sealed test | Prospective reserve beginning after the cutoff and 120-minute embargo, once enough complete blocks exist | Report every predeclared metric and failure exactly once. No retry, threshold adjustment, or model selection. |

Within every scan, use the existing deterministic randomized observation mask.
Candidate identity, tau and CFO are fit only on its training rows. Validation and
test rows may evaluate the frozen hypothesis but may not re-rank candidates,
retime trajectories, refit CFO or choose a location using evaluation rows.
Refitting the geographic location on each validation/test instance's **training
rows** is permitted when it is a frozen part of the protocol. Catalogue discovery must
use every causal eligible member in training; a retained top-K evaluation set is
labelled training-selected full-catalogue retention and preserves the full
catalogue prior mass.

The split authority should be a versioned inventory digest, fixed whole-block
assignments and a public configuration digest. Add temporal-embargo sensitivity
between development and retrospective validation. The joint-search owner should
confirm that partitions have no shared session, observation ID, or reused
candidate-selection receipt. If the same satellite appears in several sets it
is not a leak by itself, but learned source-specific orbit corrections must be
fit separately inside each partition or disabled on validation/test.

## Duration ladder

Evaluate the same frozen specification at one scan (nominal 300 seconds), about
one hour, about three hours and about eight hours. The window is elapsed
wall-clock time from its first usable capture; separately report
actual capture seconds, scan count, track count and one-second-equivalent track
weight. Gaps between planned captures are not observed RF and must never be
counted as duration or independent evidence.

For each duration, construct non-overlapping blocks within a partition. Do not
slide overlapping windows and quote them as repeated trials. If a shorter window
is nested inside a longer one, show the nested relation and use only one of them
for a primary distribution; use the other as a paired sensitivity plot. This
tests whether longer support improves a generalizing estimate rather than
selecting the best favourable capture interval.

## Ranked experiment matrix

| Rank | Frozen comparison | Training choice | Validation gate | Sealed-test report |
|---:|---|---|---|---|
| 1 | Full-catalogue hard training-MAP + null vs retained-support soft mixture | `K`, signal/null scales and candidate batching from train only | Predictive frequency score, null rate, omitted-tail audit and scan-block stability | All duration blocks, selected location/error distribution and unmatched count |
| 2 | Per-track CFO baseline vs CFO + one bounded receiver-clock term vs CFO + one bounded scan timing term | Bounds and one nuisance family | Improvement must repeat across validation blocks without information-rank loss or bound pile-up | Same fixed model, rank/condition, nuisance boundaries and error distribution |
| 3 | IID duration weighting vs predeclared AR(1)/robust grouped likelihood | One correlation/loss configuration | Better validation score without concentrating weight in a few tracks; leave-one-scan stability | Grouped error and predictive-score distribution, effective sample accounting |
| 4 | Nominal orbit vs shared source-rate correction | Only repeat-source threshold, prior and exact-replay tolerance | Repeated-source support, full-rank information and exact replay pass | Include a no-correction control and rate posterior/bound diagnostics |
| 5 | Dual-RX differential term | Calibration uncertainty and simultaneous-pair eligibility | Beats Doppler-only on paired validation blocks and permutation null | Calibration receipts, paired coverage, error distribution; no cross-dwell phase continuity claim |

## Success criteria and embargo

The primary target is **median test horizontal error at most 300 m and 90th
percentile at most 600 m** across complete, non-overlapping test blocks at the
predeclared duration. Treat failed fits as `+∞` in this primary error
distribution, so a fit-rate threshold cannot hide failures. Also report spatial
spread across retained training basins, explicit failed/boundary solutions, and
nuisance-bound pile-up. The
300 s, 1 h, 3 h and 8 h ladder must be reported separately; a success at eight
hours does not imply a 300-second capability.

Before the test is opened, freeze source hashes, location search region/seeds,
catalogue/TLE rule, masks, model choice, all thresholds and plotting code. The
test operator may run it once. A runtime or integrity failure is reported as a
failure. An infrastructure-bug fix that demonstrably cannot inspect outcomes
may be rerun with an auditable before/after proof; a scientific model change
after unsealing requires a new future test partition.

Three independent eight-hour blocks are useful preliminary evidence, but are
far too few to calibrate a strong 90th-percentile claim. Report their individual
outcomes and use the prospective reserve to enlarge the distribution.

Even a successful single-station test would establish temporal/pass
generalization at that station only. It would not establish geographic
generalization: receiver geometry, calibration, sky coverage and local
obstructions are shared. A second independently calibrated station is required
for a cross-site claim.

## Main leakage risks

1. Choosing a duration, block, seed, nuisance bound, robust floor or candidate
   threshold after examining reference error.
2. Letting randomized evaluation rows choose identity, tau, CFO, an orbit rate
   or a spatial basin.
3. Reusing selected identities, orbit corrections or calibration fits across
   train and validation/test without a partition-local refit.
4. Treating overlapping windows, adjacent samples, dual receivers or repeated
   appearances of a source as independent trials.
5. Calling a production-shortlist replication a full-catalogue blind result, or
   describing an uncalibrated soft posterior as an identity probability.
