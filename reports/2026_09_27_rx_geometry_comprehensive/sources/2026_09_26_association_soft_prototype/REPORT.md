# Soft assignment and ambiguity rejection: bounded offline prototype

This experiment examines six previously identified location-error cases from
2026-09-26 and four successful controls. It uses saved observations and causal
TLE evidence. The cases were selected after inspecting geographic errors, so
this is a diagnostic experiment, not an unbiased performance benchmark.

## Questions

1. Does keeping several satellite alternatives improve location selection over
   a hard winner when both methods receive exactly the same locations?
2. Does penalizing tracks with a small best-versus-runner-up satellite RMS gap
   help, and how much evidence becomes unresolved?
3. Can improved results instead be explained by pooling the published
   Sacramento and Reno location proposals and refining around them?

## Comparison design

The proposed locations come only from the published selected locations and a
fixed 3-by-3 local grid around each: east/north offsets of -12.5, 0, and
+12.5 km (18 proposals per scan before regional eligibility filtering).
A larger grid was considered during the canary work, then narrowed to keep
the full ten-scan replay bounded. Reference coordinates must not generate seeds,
select a method, or tune a threshold. The known receiver position is used only
to evaluate the selected outputs. Each regional comparison retains its radius
constraint. Every method uses the same proposals and evidence denominator.

The production-compatible hard baseline fits each candidate's time shift and
frequency offset on training observations and selects identities using the
existing evaluation RMS. The soft and rejection variants are ablations of that
selection score. These scores, weights, and reused evaluation observations do
not establish calibrated probabilities or independent predictive accuracy.

Soft variants retain the best three distinct satellite identities and average
their capped squared residuals with heuristic weights. Rejection variants
assign the existing unmatched penalty to ambiguous tracks; they do not remove
those tracks from the score denominator. The latter is deliberately different
from merely withholding a satellite label, which need not discard location
evidence.

The soft weights are proportional to `exp(-(r_j-r_best)/T)`, for the top
three distinct identities, at T = 5, 10, and 20 Hz. The loss is the weighted
mean of each identity's `min(r_j, 800)^2`. Margin thresholds are 5, 10, and
20 Hz; a margin strictly below the threshold (or fewer than two usable
identities) incurs `800^2`. All arms retain the original represented-second
track weights and fixed denominator. None of these settings was optimized
against reference location errors.

Seeded randomized splits of whole time bins measure conditional identity sensitivity.
There are 32 splits per track, each assigning a rounded 60% of its occupied
one-second bins to training and the rest to scoring. Each split refits time
shift and frequency offset, then selects among the original top-three
identities at the fixed published location. The seed and every bin assignment
are recorded. This tests sensitivity to the partition, not location spread.
It does not establish that one-second bins are statistically independent, or
that satellites outside a retained alternative set could not become winners.

## Baseline observations

| Capture UTC | Session suffix | Sacramento error, km | Reno error, km | Cross-prior identical assignments |
|---|---|---:|---:|---:|
| 07:50 | ddf7aff744cdaa64 | 5.791 | 428.033 | 0/42 |
| 08:10 | 3228d496423f0b3d | 5.791 | 675.822 | 0/39 |
| 08:50 | dc1153010e57ac76 | 128.932 | 123.533 | 38/39 |
| 10:10 | b44838513401b406 | 5.791 | 214.823 | 1/39 |
| 10:30 | fadea8b51ac3a4f7 | 18.287 | 687.959 | 0/51 |
| 12:50 | d86e8f23c0624bac | 13.444 | 706.761 | 0/46 |

Controls are `006056cf3db5b95a`, `4fc9ccc9f49e637b`,
`46191a1f3cafd8ca`, and `888fc1e1e005ded3`, all prefixed `scan-fw-`.
Both published branches of every control are within 11 km of the reference.

The earlier approximately 9 Hz comparisons were aggregate location-score
differences, not per-track satellite margins. Some earlier receiver-region
comparisons used coarse cells, so they cannot exclude search coverage as a
cause. The 08:50 selected locations lie northwest of the reference; an earlier
conversation described that direction incorrectly.

## Six error-case results

All three soft-weight temperatures choose exactly the same location as the
hard baseline for both priors in every error case. Merely making both
published winner locations available to the hard scorer gives the same
error-case results as the expanded local grids. This isolates a proposal/search
coverage benefit from any soft-assignment effect.

| Capture UTC | Published Reno error, km | Shared-proposal hard | Soft T=5/10/20 | Reject <10 Hz |
|---|---:|---:|---:|---:|
| 07:50 | 428.03 | 5.79 | 5.79 | 22.27 |
| 08:10 | 675.82 | 5.79 | 5.79 | 14.37 |
| 08:50 | 123.53 | 123.53 | 123.53 | 132.12 |
| 10:10 | 214.82 | 5.79 | 5.79 | 5.79 |
| 10:30 | 687.96 | 18.29 | 18.29 | 13.68 |
| 12:50 | 706.76 | 706.76 | 706.76 | 699.49 |

Reno cases above 100 km drop from six to two with shared proposals. Their
median drops from 551.93 km to 12.04 km, and mean from 472.82 km to 144.33 km.
Soft weighting adds no location-selection improvement. The 10 Hz rejection
variant improves two cases, worsens three, and leaves one unchanged relative
to the shared-proposal hard baseline; two catastrophic errors remain.

For Sacramento the shared-proposal hard errors are 5.79, 5.79, 123.53,
5.79, 18.29, and 13.44 km. Rejection at 10 Hz improves two, worsens three,
and leaves one unchanged. No tested margin threshold resolves the remaining
catastrophic location failures.

## Why a small-margin gate does not identify the bad locations

The following margins compare distinct satellite identities at the exact
originally published Reno locations, after each candidate's nuisance fit.

| Capture UTC | Median identity margin, Hz | Tracks with margin <10 Hz | Duration weight with margin <10 Hz |
|---|---:|---:|---:|
| 07:50 | 103.9 | 5/42 | 7.9% |
| 08:10 | 48.4 | 9/39 | 8.5% |
| 08:50 | 416.1 | 3/39 | 3.6% |
| 10:10 | 99.8 | 8/39 | 7.3% |
| 10:30 | 125.3 | 14/51 | 15.8% |
| 12:50 | 96.8 | 4/46 | 3.3% |

Wrong locations can have clear winners within their local candidate inventory.
At the 10 Hz gate's chosen 08:50 and 12:50 locations, no tracks are rejected,
yet the errors are 132.12 and 699.49 km. Searching with this penalty can favor
locations with more decisive assignments without making those assignments
geographically correct. A decision to withhold an uncertain label is different
from imposing a large penalty on location inference.

## Controls, stability, and verification

All four good controls also choose identical locations under hard assignment
and every tested soft temperature. Their mean error under the shared-proposal
baseline is 7.06 km for each prior. Rejection raises that mean to 9.71 km
(5 Hz), 14.90 km (10 Hz), or 18.08 km (20 Hz), with a maximum of 26.05 km.
Pooling itself is not universally beneficial: it changes which original prior
winner is selected, and a lower score can modestly increase geographic error
on a good control. All shared-proposal hard control errors remain below 10 km.

Every hard and soft winner is an original published zero-offset seed. The
local refinements provide no additional selected-location benefit in this
sample. Rejection variants sometimes select the local grid boundary, so their
numerical locations are additionally sensitive to the bounded proposal set.

The randomized split test confirms that bad locations can have locally stable
identities. At the originally published Reno locations:

| Capture UTC | Median original-winner frequency over 32 splits | Duration-weighted original-winner frequency | Tracks below 75% |
|---|---:|---:|---:|
| 07:50 | 98.4% | 91.8% | 8/42 |
| 08:10 | 100.0% | 85.8% | 14/39 |
| 08:50 | 100.0% | 93.5% | 5/39 |
| 10:10 | 100.0% | 90.0% | 11/39 |
| 10:30 | 96.9% | 87.5% | 15/51 |
| 12:50 | 100.0% | 90.2% | 12/46 |

For the four good-control Reno branches, duration-weighted original-winner
frequency spans 88.4%-95.7%, overlapping the failures. A small subset of tracks
is unstable in either group. These frequencies are conditional on the original
top-three identities and fixed published locations; they cannot measure
global association uncertainty or serve as calibrated correctness probabilities.
The randomized splits are exploratory sensitivity checks on reused evidence.

The final ten-scan scoring replay ran in two batches, taking about nine minutes
of elapsed wall time (1,054 seconds summed across per-scan elapsed times).
Original hard scores reproduced at all 20 published prior winners, with maximum
absolute difference below 6.4e-12 Hz. Evidence and TLE snapshot bindings matched.
Eight focused tests pass in the deployed runtime: global distinct-ID merging,
missing/invisible candidates, conservative one-candidate rejection, exact
threshold handling, fixed denominator, soft/hard behavior, seeded whole-bin
partitioning, offset refitting, and visibility handling.

The experiment was implemented and independently reviewed with SOL delegates.
No production search, queue, service, public contract, or golden fixture was
changed. No new RF collection was performed.

## Interpretation

The evidence supports sharing independently generated location candidates
between the two regional searches, subject to each region's radius. Four
apparently ambiguous Reno failures had a better-scoring Sacramento-generated
candidate that was already available. This corrects the earlier suggestion
that search coverage was probably unimportant.

This particular top-three soft expected-loss heuristic adds no selected-location
benefit on these ten scans. It does not test every probabilistic association
method or exclude benefits from a properly specified joint likelihood.
Penalizing small identity margins is unreliable here and can favor confidently
wrong locations. Withholding an ambiguous satellite label remains reasonable
as a reporting policy, but should not be mistaken for a validated location fix.

The two remaining large-error cases require additional constraints or evidence
that distinguishes competing location/identity explanations. A clean next
validation would freeze the candidate-sharing rule and evaluate it on separate
randomly grouped scans without selecting cases or tuning thresholds by their
known errors.

## Artifacts and reproduction

- `run_prototype.py`: bounded full-catalogue scoring experiment.
- `results.json`: combined ten-scan results with every candidate point and
  retained top-three per-track scores; `results-a.json` and `results-b.json`
  preserve the original batch inputs bound by stability results.
- `comparison.md`: all methods for both priors, case/control statistics, and
  unresolved track counts and duration weights.
- `stability.py`, `stability-a.json`, `stability-b.json`: conditional split
  sensitivity, with seeds and per-replicate bin assignments.
- `test_prototype.py`, `test_stability.py`: focused numerical/protocol tests.

Frozen scorer SHA-256:
`9f4160d5c50b1f69332bb758ea4cae4bd4d17933b274e46207ab5e635b08a375`.
The deployed scorer and prediction modules used for replay match the source
in the adaptive-position deployment worktree. Replay requires the retained
recordings, analysis products, causal TLE archive, and deployed Python runtime.

From the repository root, a single-case reproduction is:

```bash
sudo -n -u leo /opt/leo-tracker/current-api/.venv/bin/python \
  reports/2026_09_26_association_soft_prototype/run_prototype.py \
  --output /tmp/association-replay.json ddf7aff744cdaa64

sudo -n -u leo /opt/leo-tracker/current-api/.venv/bin/python \
  reports/2026_09_26_association_soft_prototype/stability.py \
  /tmp/association-replay.json --output /tmp/association-replay-stability.json

sudo -n -u leo /opt/leo-tracker/current-api/.venv/bin/python -m pytest \
  -q -p no:cacheprovider reports/2026_09_26_association_soft_prototype/test_prototype.py \
  reports/2026_09_26_association_soft_prototype/test_stability.py
```

For exact reproduction, use the deployed release resolved during this run,
`/opt/leo-tracker/releases/e1a24b200d4bb68d4f38484dc591e9b9616a2e70`,
in place of the mutable `current-api` alias.
