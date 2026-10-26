# Independent qualification protocol v1

Frozen 2026-10-26 20:39 UTC, before inspection of new candidate outcomes in
`revisit/` or `frequency/`. Changes after outcomes require an explicitly labeled
new exploratory protocol; they cannot retroactively qualify this iteration.

## Scope and authority

The development panel is DS24-0010..0013, channels 5..8 with channels 1 and 4
controls, two later revisit targets per scan/channel: 48 paired targets and
96 receiver cells. Missing and ambiguous cells stay visible. Earlier-only
same-channel/receiver/edge donors may condition a later estimator. A full-scan
track fit, target samples, GPS, a recovered satellite identity or a localization
outcome may not select donors, hypotheses or estimator parameters. The four
exposed scans establish development behavior only, never new-location transfer.

The exact current ALGO/baseline implementation, native source contracts,
precision, masks, timestamps, candidate inventory and TLE authority must be
identified and hashed before an adapter can be called ready. Reference projects
are numerical oracles only. No frozen scientific artifact is rewritten.

## Sequential RF gate

1. **Measurement accuracy:** frozen known-truth controls must include signal
   absence, donor frequency errors of both signs, nonzero frequency evolution,
   multiple modes and unchanged final-bin and carry-only comparators. Report
   paired CFO error distributions, catastrophic failures and availability, with
   identical samples/hypotheses/budgets. To qualify an accuracy improvement,
   paired median absolute CFO error must improve over both comparators and the
   upper tail must not worsen; uncertainty must cover donor-error/rate regimes.
   If an upper tail or accuracy claim is too sparsely sampled, mark inconclusive.
2. **Uncertainty:** a GLRT margin, softmax of arbitrary scores or an uncalibrated
   mode weight is not a physical likelihood or standard deviation. Coverage
   must be measured on controls not used to tune calibration, including donor
   error and nonzero evolution. Report nominal 68/95 percent coverage with
   binomial uncertainty; empirical undercoverage inconsistent with nominal at
   95 percent confidence fails. Multimodal solutions retain modes and shared
   ownership, or remain unavailable for point-observation integration.
3. **Independent natural support:** each proposed native target detection or
   correction needs later raw samples with explicit native support, distinct
   from every donor. It must show target evidence conditional on the same
   earlier donor state against the unchanged target estimator and carry-only
   state. Injection-only improvement cannot qualify natural points. Raw support
   integrity, same-support modes/aliases and target/donor overlap are audited.
4. **Multiplicity and nulls:** declare every opened target, receiver, mode,
   timing/frequency/rate/edge proposal and adaptive attempt, including failures.
   Conditional null experiments retain the donor state and search exposure.
   For positive admission require a predeclared batch family-wise false
   confirmation bound <=0.05. Report null trials, confirmations, exact one-sided
   95 percent binomial upper bound and exposure correction. Unadjusted margins,
   zero observed false alarms with too few trials, or donor-correlated trials
   counted as independent fail the positive-admission gate. A conservative
   Bonferroni bound is allowed; alternatives require independently justified
   dependence handling. An unqualified branch may still be a useful negative
   screen.
5. **Ownership:** one raw target observation has one likelihood owner.
   Corrected existing measurements replace the exact existing owner; newly
   detected native targets need disjoint support or explicit joint covariance.
   Donors remain baseline observations/conditioning; copying a donor forecast
   does not create a second measurement. Receiver/family correlations must be
   carried explicitly, or paired/grouped conservatively. Overlapping aliases,
   candidate modes and repeated estimates do not increase observation count.

Every gate is required; an unknown gate blocks propagation. No natural
candidate is admitted merely because a synthetic estimator improves or an
in-sample fit increases. Existing accepted baseline points are replayed unchanged
while new proposals remain quarantined.

## Baseline and position readiness

The adapter distinguishes `correct_existing` and `new_native_detection` and
requires exact source/hash/owner identity. It preserves raw target IDs, native
sample coordinates, receiver and band offsets, aliases, timestamp precision,
channel/edge and actual RF. Frequency conversion uses actual RF, not a nominal
copied band center. A correction changes only its measurement and justified
uncertainty; existing support and unrelated observations remain unchanged.

Before localization, seal observations, candidate catalog, causal TLEs and
priors. Candidate sets/observations/other priors/search budgets and starts must
match between c=0 and fitted-c. Region: 25 by 25 km centered at
37.906,-122.545. No forced recovery identities or GPS-selected subset. GPS may
be opened solely for post-seal error reporting. Report frequency-fit/score and
position accuracy separately, preserving all-channel baseline, channels 5..8
effect, tails and unavailable cases. More detections or a better in-sample
frequency fit alone do not demonstrate localization improvement.

A qualified manifest and ready STATUS are handed to the primary agent before
any candidate localization run; primary approves that dependency execution.
If RF qualification fails, deliver tests, baseline receipt and explicit blocking
reasons without forcing associations or a position run.

## Resource and write bounds

Only `validation/` is writable by this branch. Use apply_patch for handwritten
files. No git changes/push, production changes, new RF or QNAP writes. All
numerical commands use BLAS1, <=2 workers and <=600-second outer timeout. Do not
wait on or launch multi-hour campaigns.
