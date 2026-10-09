# Proposed no-fit ambiguity census

Prepared code only: **no protocol has been frozen and no recording evaluated**.
Execution requires parent review, immutable source/input hashes and worker capacity.

Use all 148 historical consumed members (63 DS16, 51 DS17, 34 DS18) from the
iteration106/87 frozen bindings, preserving DS16 original/added and DS18 exposure
labels. Evaluate ordinary archived iteration85 B7 endpoints, not iteration106's
100 Hz candidates or selectively recovered examples. No reference coordinate or
position error constructs the numerical model, groups rows, or selects endpoints.

The inherited loader does access an archived error field for provenance. As
documented in [the source dependency audit](../2026_10_09_position_error_iter106/REFERENCE_DEPENDENCY_AUDIT.md),
iteration51's `legacy_ds16` branch compares persisted `horizontal_error_m` for
exact equality against its pinned recovery receipt, along with objective,
selection score, source basin and satellites. A mismatch can cause an input
failure; the value is not thresholded, optimized or used to select observations.
Full document hashes also bind reference-bearing metadata. This is an artifact
admission dependency, so **no reference-guided inference** is accurate while
**no reference-field access anywhere in the loader** would be inaccurate. The
immutable loader remains unchanged and any such failure is reported explicitly.

Reconstruct through immutable iteration87 exactly once per member, retaining
the same loader's prepared bootstrap memberships. The source is unchanged: the
driver copies its function namespace only to capture the loaded prepared case.
Verify both saved objectives within 1e-6. Use one shared metadata-only segment
layout for both c arms: same receiver/channel/exact RF, positive gap at most
2 seconds, unique track membership, no bridge across overlap exclusions, uncovered
rows independent. Every observation occurs exactly once. Zero-c static and RF-time
locks are checked.

Recreate the production predictions including receiver baselines, smooth/RF-time
clock terms and satellite slope corrections. Run the persistence kernel **only
at rho=0**, using the packed segment layout. Restore original prediction-gradient
row order. Require whole objective parity within 1e-6 including all unchanged
timing/clock priors, and prediction-gradient maximum absolute difference at most
1e-12. No positive persistence strength, optimizer or model winner is evaluated.

Record full coverage, singleton/linked segment counts, eligible links, overlap and
uncovered rows, and every boundary reason. Per arm, describe posterior entropy in
nats, log top-two odds, clutter and maximum probability distributions separately
for all rows, linked rows and independent rows. Confidence bins below 0.5,
0.5–0.9 and at least 0.9 are fixed descriptive thresholds, not selection rules.
Count label switches on eligible links, separating satellite-to-satellite,
clutter-involving and both-endpoints-at-least-0.9 satellite switches. A switch is
not labelled an error. No grouping depends on these measurements.

Every frozen member receives an append-only complete or failed receipt; failures
retain partial coverage/arm checks and an explicit reason. Full-census summaries
must withhold full metrics when members are missing or failed, and label available
diagnostics as such. No uncertainty/independence or held-out validation claim is
made: tracks were constructed from these measured CFOs and all data are consumed.

Expected command after a separate freeze: `audit.py --shard 0|1`. At most two
single-thread workers, coordinated with other research jobs. Source closure must
include the inherited reconstruction/input authorities plus `audit.py`,
`segments.py`, `persistence.py`, their tests and this protocol. No RF collection,
production source changes, reserve access or geographic selection is involved.
