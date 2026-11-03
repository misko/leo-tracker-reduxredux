# Whole-track noise evidence inside satellite/position fitting

This experiment implements the residual-aware criterion inside parameter
updates and geographic ranking, then evaluates actual position error. Both
DSX01 scan 1 and DS22 scan 001 have paired c=0/fitted-c runs and matching
legacy-objective controls. The results below are resumed blind local searches,
not global convergence or independent satellite identity validation.

## Controlled search and association

All methods use the same causal candidate banks, radio-only robust partitions,
original measured CFOs / times / RF / IDs, and scan-specific receiver/band
offsets and small drifts (sigma 0.5 Hz/s, bound 1 Hz/s). Each c pair starts from
the same earlier **blind c=0** position and eight hardware coefficients; fitted-c
adds a zero initial c. The new method also receives the same blind phase vector
in both c arms. No known-position phases or hardware enter a blind search.

Only individually measured-curved fragments can rank geographic states or
calibrate hardware/phase. The score applies all candidates' visibility, RMS
450 Hz, component-constant 3,000 Hz, member mean/slope/quadratic/step/lag-1 gates
before choosing a winner. Failed components pay the declared capped-count
900 Hz squared cost. Bias, drift, phase, conditional phase-volume and hardware
dimension penalties remain. The same original measurements contribute; there
is no point holdout or smoothing. Gates are finite-sample diagnostics, not a
guarantee of white noise or correct identity.

The new solver generates two proposals at each location (previous blind state
and legacy fit), takes up to two feasible-component joint updates per tangent,
and accepts only new-score improvements. Linear / failing tracks cannot update
parameters. Three finalists are checked under exact nonlinear phase geometry,
with up to four relinearizations for each proposal. An exact score, rather than
a tangent score, chooses the reported endpoint.

Both algorithms search a fixed 3x3 grid of +/-16 km around their common blind
start, followed by up to two axial sweeps at 8, 2, 0.5 and 0.125 km. The cap is
41 discovery locations with 4 generated legacy seeds; three exact finalists use
8 generated seeds. Actual visited locations can differ because rankings differ.
The new method spends additional feasible-update work, so this comparison
matches declared geographic / seed budgets, not CPU instructions. Final
association uses the same candidate-after-gates logic for both algorithms, then
requires curved hardware/phase support before admitting linear fragments.
Lossless shared-constant merging checks every member and pooled residual with
a maximum 30 s gap; it does not itself refit the position.

## Blind endpoints

On these matched local searches, the new method reduces error from 11.968 km
to 8.367 / 8.501 km on DSX01-S01 (c=0 / fitted-c), and from 12.924 km to
3.241 / 1.895 km on DS22-001. No endpoint meets the 0.5 km target. Fitted-c
helps DS22 accuracy here, but on DSX01 associates more points while giving a
slightly larger position error. These two scans cannot establish a general
accuracy advantage for fitted-c.

| Dataset | c arm | Method | Error km | Associated | % raw GLRT | Merged tracks | Points/track |
|---|---|---|---:|---:|---:|---:|---:|
| DSX01-S01 | c0 | Legacy | 11.968 | 1,700 | 35.44% | 60 | 28.3 |
| DSX01-S01 | c0 | Noise-gated | 8.367 | 2,490 | 51.91% | 70 | 35.6 |
| DSX01-S01 | fitted_c | Legacy | 11.968 | 1,700 | 35.44% | 62 | 27.4 |
| DSX01-S01 | fitted_c | Noise-gated | 8.501 | 2,509 | 52.30% | 91 | 27.6 |
| DS22-001 | c0 | Legacy | 12.924 | 998 | 24.71% | 36 | 27.7 |
| DS22-001 | c0 | Noise-gated | 3.241 | 1,632 | 40.41% | 50 | 32.6 |
| DS22-001 | fitted_c | Legacy | 12.924 | 1,083 | 26.81% | 40 | 27.1 |
| DS22-001 | fitted_c | Noise-gated | 1.895 | 1,602 | 39.66% | 47 | 34.1 |

Percentages use 4,797 raw GLRT points for DSX01-S01 and 4,039 for DS22-001,
including points outside the 4,487 / 3,510-point Graph populations. One S01
measurement remains explicit background; DS22 membership is unchanged. GPS
37.849061591561885, -122.48574968092912 is used only after saving each blind
endpoint. Observer height is fixed at 0 m in all models. Endpoint hashes bind
the evaluations. Better fit or association
coverage must not be read as better position accuracy.

![Accuracy and association comparison](comparison.png)

![GLRT association panels](track_associations.png)

![Merged-track RMS distributions](merged_track_rms.png)

`merged_track_rms.json` records RMS, members, candidate and point count for every
merged track. RMS is recovered from the saved Gaussian contrast after removing
its constant-prior and volume terms (150 Hz noise, 1,000 Hz bias prior). The plot
sorts each method independently; equal ranks do not imply matching identities.

## Label stability and independent-arc support

The comparison below uses original observation IDs, not curve resampling or
time-nearest matching. Changed NORAD means both methods associate the same
measurement but nominate different objects. Stability is not identity truth.

| Dataset | Comparison | Common points | Changed NORAD | Gained / lost |
|---|---|---:|---:|---:|
| DSX01-S01 | legacy_control/c0 -> search/c0 | 1137 | 61 | 1353 / 563 |
| DSX01-S01 | legacy_control/fitted_c -> search/fitted_c | 1293 | 61 | 1216 / 407 |
| DSX01-S01 | search/c0 -> search/fitted_c | 2334 | 0 | 175 / 156 |
| DS22-001 | legacy_control/c0 -> search/c0 | 761 | 0 | 871 / 237 |
| DS22-001 | legacy_control/fitted_c -> search/fitted_c | 761 | 0 | 841 / 322 |
| DS22-001 | search/c0 -> search/fitted_c | 1567 | 0 | 35 / 65 |

The two new c arms agree on NORAD for all 2,334 common S01 points and all 1,567
common DS22 points. Against the old control, 61 common S01 points change NORAD
in each c arm and no common DS22 points do. Much of the gain is a change in
which fragments pass, rather than a wholesale relabelling of shared points.
Agreement across these variants still does not supply external identity truth.

For each new fit, count satellites supported by only one measured-curved
fragment. Multiple fragments do not necessarily mean independent passes or
independent calibration; this is a descriptive support inventory.

| Dataset | c arm | Single-curved-fragment satellites / all | Their points / curved points |
|---|---|---:|---:|
| DSX01-S01 | c0 | 9 / 21 | 230 / 1519 |
| DSX01-S01 | fitted_c | 11 / 22 | 341 / 1522 |
| DS22-001 | c0 | 8 / 16 | 269 / 1123 |
| DS22-001 | fitted_c | 8 / 16 | 232 / 1086 |

## Conditional random-intercept diagnostics

For each new final state, 16 deterministic randomizations add an independent
uniform native-period intercept to each curved fragment. Times, centered curve
shape, noise and RF remain fixed; parameters, phases and position remain frozen.
Both c arms use identical random draws. Candidates and gates remain unchanged.
The table reports only curved points, which are the observations allowed to
calibrate; these counts differ from total associated Graph points above.

| Dataset | c arm | Actual curved points | Null min / median / max |
|---|---|---:|---:|
| DSX01-S01 | c0 | 1519 | 0 / 42 / 114 |
| DSX01-S01 | fitted_c | 1522 | 0 / 52 / 139 |
| DS22-001 | c0 | 1123 | 0 / 25 / 110 |
| DS22-001 | fitted_c | 1086 | 0 / 25 / 110 |

This is a conditional frequency-coincidence check, not an end-to-end null search,
an authenticated label test, or a calibrated false discovery rate. It does not
measure how often reoptimizing hardware, phases and position on null data would
recover apparent tracks. That stronger test remains outstanding.

## Separate post-search known-position diagnostics

Only after completed blind endpoints and nulls are saved, a separate tool fixes
the supplied GPS and runs the new fit with the same blind initializer/budget.
It also refines an earlier known-position fit as a distinct initialization
sensitivity check. Neither diagnostic is fed into the reported searches.
Scores below are new composite scores in millions; lower is better. Historical
known-position initialization has information unavailable to a blind search.

| Dataset | c arm | Blind endpoint | GPS / blind start | GPS / historical GPS start |
|---|---|---:|---:|---:|
| DSX01-S01 | c0 | 1095.53 | 1243.95 | 1196.69 |
| DSX01-S01 | fitted_c | 1093.78 | 1197.39 | 1196.86 |
| DS22-001 | c0 | 1139.13 | 1238.39 | 1235.72 |
| DS22-001 | fitted_c | 1165.16 | 1346.86 | 1304.54 |

All four new blind endpoints score better than both tested GPS initializations.
Thus integrating residual gates improves this experiment but does not make
noise-like residuals sufficient for correct positioning or identity. More
search alone has no guarantee of fixing that remaining discrepancy. These
finite proposals do not prove a globally worse optimum at GPS.

If GPS scores better, the saved wrong endpoint does not establish a globally
preferred wrong position: geographic or parameter proposal search still misses
a better state. If a wrong endpoint beats tested GPS states, that is evidence
of a model/criterion mismatch within the tested proposals, not proof that all
GPS states are worse. The larger <0.5 km objective remains unachieved unless
independent, representative results meet it; these two scans alone cannot
establish performance on the full DS22 and DSX01 corpora.

The next diagnostic should transfer each saved blind candidate family to GPS
with identities fixed, then refit only allowed shared hardware/phase parameters
on measured-curved fragments. That separates a failure to propose good
parameters at GPS from incompatible candidate families or a frequency-model
error. It must remain separate from blind search and must not promote a
GPS-derived parameter state into a localization result. Shared-constant merged
families and independently curved members can then supply stronger joint
constraints without recruiting linear fragments for calibration.

## Validation and reproducibility

Thirty-five focused tests passed for robust membership, preserved original IDs,
provided-population consolidation, phase profiling, candidate-after-gates
association, linear association without calibration, and monotonic new-score
updates. Independent dense point residuals agree with tangent sufficient
statistics for c=0 and fitted-c, including nonzero phase anchors. All changed
scientific sources pass Ruff. Code snapshots bind the run versions; bank and
partition receipts bind the same durable inputs as the previous repair report.
All runs use existing on-disk observations; no RF collection was performed.

The result directories preserve every endpoint, trace, exact finalist,
association, original observation ID, merged component, null draw summary and
GPS-only diagnostic. `validation.json` binds endpoint hashes. This is a research
prototype; published contracts and baseline reports are unchanged.
