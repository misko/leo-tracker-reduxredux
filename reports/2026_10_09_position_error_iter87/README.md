# Iteration87: full148 B7 residual audit before another model extension

Prepared protocol; no new fit or accuracy result. This audit reconstructs every
accepted immutable iteration85 B7 endpoint in both c arms and verifies its
objective within1e-6 before summarizing residuals. It invokes no optimizer.
All63 DS16,51 DS17 and34 DS18 recordings remain in coverage, including explicit
input, reconstruction or statistics failures. These are consumed development
recordings, not independent validation. Production B7 is unchanged.

The [research memo](../2026_10_09_position_error_iter86/NEXT_MODELS.md) requires
this audit before prototype fits: historical paired receiver offsets and serial
correlation predate B7 and may already be explained by its joint-clock, RF-time
and satellite-slope stages. No physical hardware explanation or localization
benefit follows from residual structure alone.

## Frozen grouping and statistics

For every window, the highest B7 fitted-c satellite responsibility must be
strictly greater than0.5 to assign a satellite. All other windows remain counted
as unassigned. Freeze this assignment and confidence for both c arms. Residuals
are arm-specific wrapped measurement-minus-prediction values for that component.
No reference position, reference error, or per-scan outcome selects a group.

Receiver pairs require the same inferred satellite, channel, and observation
time rounded to milliseconds. Average duplicate observations within each receiver
before forming RX1-minus-RX0. No nearest-time substitution. Report counts and
mean/median/standard-deviation/RMS differences for every satellite with pairs.
A satellite with at least10 pairs is eligible for the proposed future contrast
model; fewer than2 eligible satellites gives its explicit no-op condition.
This is an inference-only diagnostic eligibility count, not a data exclusion or
an implemented correction. Report complete membership and missing-input failures.

Within each satellite/receiver/channel, use adjacent residuals at strictly
positive gaps no larger than2seconds. Report correlation only with at least10
pairs and nonzero variance. These pairs may share observations; correlations
are descriptive, not independent-sample significance or effective sample sizes.
Original GLRT margin is summarized descriptively against signed/absolute
residuals; it is not elevation margin, SNR, or calibrated frequency uncertainty.

The c comparison is conditional: assignments, observations and bank are shared
and fitted-derived. Static c and both RF-time terms remain locked to zero in the
c0 endpoint. No measurement weighting, candidate bank, seed, region retention,
hyperparameter or operational winner changes. There are no new position results.

## Execution and reporting

`freeze.py` seals code, model dependencies, immutable input closure and all148
endpoint files before `audit.py` executes. Source/input digests are verified
before each shard starts. Result receipts are append-only; a failed member is
retained rather than silently retried or dropped. Preparation does not authorize
numerical execution: launch only after parent capacity approval, with at most
two single-thread workers. Never resume or mutate iteration83/84 from this audit.

Report per-dataset/arm distributions, receiver-pair and eligibility coverage,
serial-correlation and margin summaries, and every failure. Keep frequency
diagnostics separate from accuracy. The next model hypotheses remain proposals;
any later fit requires a frozen matched-c protocol and randomized whole-group
development/validation design. The post-DS18 reserve remains closed. No RF
collection, production change, or independent-validation claim occurs here.
