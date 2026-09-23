# Train/validation/test plan and model priorities

The sub-300 m target is not yet demonstrated. The older approximately 300 m result
was development evidence; broader checks have not reproduced that accuracy.
The new blind causal-catalogue baseline improves with multiple scans but remains
about 10 km from the reference. More precise grid coordinates do not establish
more accurate positioning.

## Frozen dataset

The [machine-readable manifest](../2026_09_23_long_inventory_complete/manifest.json)
assigns whole eight-hour recording groups using seed 20260923, conditioned on
known earlier exposure. It is not a chronological train/test split or a random
division of correlated individual observations.

| Partition | Scans | Eight-hour groups | Permitted use |
|---|---:|---:|---|
| Train | 151 | 2 | Model development and inner randomized frequency-row checks |
| Validation | 124 | 2 | Compare frozen model families; no per-case tuning |
| Test | 64 | 1 | Keep track evidence closed until final model selection |

The nested duration views are 1, 6, 16, and all scans per group. These are
correlated views, not separate replications. Some scans have 10 MS/s recordings
while most have 2.5 MS/s; the manifest records the difference. Qualification of
validation inputs is not a validation position result. Prior historical production
exposure is unknown, and adjacent groups can share hardware and orbital errors.
The separate prospective reserve remains unopened.

## Completed blind training baseline

| Fixed TRAIN view | Tracks | Sacramento 250 km error | Reno 500 km error | Final grid spacing |
|---|---:|---:|---:|---:|
| 1 scan | 93 | 41.00 km | 40.59 km | 1.5625 km |
| 6 scans | 476 | 9.83 km | 9.85 km | 0.1953125 km |
| 16 scans | 1,130 | 10.04 km | 9.91 km | 0.1953125 km |

These completed fits are not yet full eight-hour fits. Six scans span 35.0
minutes with 30 nominal capture minutes; sixteen span 107.0 minutes with 80
nominal capture minutes. The full eight-hour groups are the frozen dataset units,
and the all-scans view remains to be fitted after these baseline diagnostics.

The six/sixteen-scan inference took 502.7 seconds in total with existing compact
state caches. It uses all qualifying tracks, full causal regional candidate
inventories, train-only per-track identity and constant-frequency-offset fitting,
fixed zero epoch correction, and a shared position. Reserved frequency rows and
the reference coordinate are scored after inference is sealed. No published
satellite identities or position seeds enter this new search.

Visibility eligibility uses the known timestamps of the whole track, including
reserved-row timestamps, but no reserved frequency values. It requires visibility
at at least one timestamp, not throughout the track. The reserved result therefore
tests frequency prediction conditional on that known observation schedule. Each
track also gets an independent identity and constant offset, including across
scans; only geographic position is shared. This does not yet exploit repeated
satellite identity or receiver-offset continuity across visits.

Refining from 1.5625 km to 0.1953125 km improves its training score by only about
0.001–0.226 Hz across these four searches. This points to a limitation of this
model/search combination rather than just its final spacing. The three-cell beam
is heuristic, so it does not rule out an unexplored basin. The different duration
views also include different tracks; their errors are not an independent learning
curve. See the [single-scan report](../2026_09_23_long_training_search/README.md)
and [joint search](../2026_09_23_long_training_search_multi/README.md).

## Next experiments and responsibilities

SOL implemented the blind joint search; Terra prepared and verified its caches,
audited public quality joins and causal orbit updates, and independently reviewed
the estimator. Keep model fitting and independent data-integrity review separate.
Do not tune scores on geographic error, open the reserved long test group, or
interpret a fine grid as accurate positioning. The following are hypotheses to
test, not demonstrated fixes.

| Hypothesis | Evidence to collect first | Bounded experiment |
|---|---|---|
| More observations resolve location/identity ambiguity | Same score and search over 1/6/16/all scans | Compare independent regional starts and randomized reserved residuals; retain failures |
| Frequency quality varies within a scan | Exact observation-to-GLRT candidate join | Train a quality-to-residual relationship on training data; compare to unchanged weights |
| Absolute UTC or orbital timing differs from host-start uncertainty | Separate host bracket from absolute-time evidence | Compare a shared epoch correction with regularized source deviations, keeping the decomposition identifiable |
| Causal orbital elements vary enough to matter | Propagate two preceding causal snapshots at identical epochs | Measure radial/along/cross-track and Doppler-shape disagreement; use it only as a variability proxy |
| Independent track offsets discard useful cross-track constraints | Repeated source/lane support and native RF scaling | Revisit a fixed shared-offset hypothesis with randomized groups, preserving integer pilot ambiguities |

The current `standard_uncertainty_hz` is not a calibrated per-peak GLRT quality
estimate. `project_scanner_candidates` assigns a scan-level floor combined with
host timing uncertainty; trajectory construction then rescales it by RF. Treating
that number as measured SNR precision would mischaracterize the available evidence.

Earlier repository work already tested shared circular offsets and found only
modest improvements, with kilometre-scale errors. Its historical temporal holdout
must not be relabelled as randomized. See the
[original report](../2026_09_22_joint_circular_position/README.md). New experiments
must justify what changes rather than repeat that result under a new name.

The causal-update audit now has a concrete result: the immediately previous two
catalogue refreshes retained identical regional elements, while the nearest older
changed boundary had about 2.7 km median absolute along-track disagreement and
about 59 Hz median three-epoch Doppler-shape disagreement after constant removal.
These are differences between catalogue solutions, not errors against orbit truth.
They justify a controlled sensitivity experiment, not assigning a 2.7 km prior
or declaring orbital error the sole cause. See the
[audit and reproducible receipts](../2026_09_23_causal_orbit_variability/README.md).

## How a sub-300 m claim would be tested

1. Develop bounded changes using TRAIN only. Keep the fixed zero-time baseline
   and report every attempted family, including failures. Use actual receiver/RF
   semantics when sharing offsets; one arbitrary offset for every track in a scan
   would be a different, potentially incorrect measurement model.
   Candidate-margin diagnostics are useful, but dropping ambiguous tracks and
   renormalizing separately at each location can reward a cell for explaining
   less data. Preserve a fixed observation budget and explicit unmatched/outlier
   cost. A candidate score gap is not automatically a calibrated probability.
2. Freeze a small candidate family set, tuning rules, duration views, search
   budget and abstention rules before position scoring on the two validation
   groups. Compare geographic errors, reserved frequency prediction, associations,
   prior-to-prior stability, and runtime together. A smaller residual alone has
   already failed to identify a better geographic solution.
3. Select one configuration using aggregate validation performance and freeze
   its source/input hashes. Run the closed test group once, with no selection or
   retuning from its coordinate error. Keep failure cases in the reported counts.
4. Report short/medium/long views separately, with actual time coverage. Passing
   a single nested long view below 300 m is one result, not a reliable 300 m
   accuracy bound. One eight-hour test group cannot support a population 95th
   percentile; that needs more independently reserved groups or prospective data.

Scientific outputs and cached inputs are reproducible report artifacts. These
experiments do not alter production analysis or authorize deployment.

## External context, not an accuracy guarantee

A primary 2025 error-budget study identifies orbital errors as the strongest
effect in its standalone Starlink Doppler setting, especially with publicly
available orbit data. It also reports dependence on observation duration and
clock stability. This motivates checking our catalogue variability; it does not
establish the cause of our measured errors. Only the public abstract was reviewed.
[Stock, Schwarz and Knopp, IEEE/ION PLANS 2025](https://www.ion.org/publications/abstract.cfm?articleID=20093).

A recent primary waveform study describes additional predictable downlink
structure and contrasts positioning demonstrations with differing bandwidth and
reference-receiver support. Our narrow recorded bandwidth and lack of an external
calibration receiver do not inherit those demonstrations' accuracy. Improved
waveform estimation is a separate avenue from declaring the current track-level
position model accurate.
[Qin et al., npj Wireless Technology 2026](https://www.nature.com/articles/s44459-026-00075-6).
