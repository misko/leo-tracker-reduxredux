# DS23 repaired arcs propagated to position error

All three association variants were propagated into full-scan position fits
for DS23-0342 and DS23-0039. **The association fixes work, but their position
benefit is mixed.** EM modestly improves 0342 relative to the matched control;
the two graph variants are slightly worse. All three increase position error
in 0039. Additional shared satellite Doppler-scale freedom increases error
for every repaired variant, despite slightly reducing frequency residuals.

The existing penalized RF objective prefers the position model without that
extra scale freedom in every case/arm. That model choice is independent of GPS.

## Main position results

Horizontal errors are great-circle distances in kilometres to the user-supplied
reference, 37.849061591561885, −122.48574968092912. That coordinate appears only
in reporting/evaluation, not initialization, association, fitting or model
selection. These are two scans, not 64 independent experimental replicates.

| Approach | 0342, c=0 | 0342, fitted c | 0039, c=0 | 0039, fitted c |
|---|---:|---:|---:|---:|
| Matched causal, gated control | **2.023** | **1.962** | **0.760** | **0.893** |
| Greedy graph repair | 2.147 | 2.105 | 1.159 | 1.286 |
| Joint path selection | 2.147 | 2.105 | 1.159 | 1.286 |
| Satellite EM, MAP assignments | **1.949** | **1.897** | 1.159 | 1.286 |

The repair rows include repeated association updates in the repaired lane at
the updated position and receiver calibration. Memberships stabilize after
two checks; the positions equal the initial fixed-association propagation
at the precision shown. The rest of each scan's RF-derived nominations are
held fixed as the common control. Thus this is full-scan position estimation
with targeted association refresh, **not** fresh discovery/reclustering of
every receiver/channel or an unrestricted satellite/position search.

![Position errors by scan and approach](position_errors.png)

For 0342, greedy/joint increase c=0 error by 124 m versus the matched control;
EM reduces it by 74 m. For 0039, every MAP variant increases c=0 error by 399 m.
These differences should not be interpreted as statistically significant
population performance from only two scans.

The older published pilot errors were approximately 5.000/4.998 km on 0342
and 3.372/3.502 km on 0039, for c=0/fitted-c. Those are **historical, unmatched
controls**: they used different phase uncertainty and included a track in
position fitting that failed its displayed association gate. The current
matched control already incorporates genuine earlier causal epochs, the
age/disagreement phase prior and exclusion of that failed calibration track.
The large improvement over the pilot must not be credited to these new
association variants.

### Comparison with the earlier corrected prototype

The matched control above is the **pre-salvage** control, not the best earlier
corrected prototype. The earlier investigation also restored a conservatively
gated 36-point suffix in 0342, producing **1.786/1.736 km** for c=0/fitted-c.
That row was omitted from the initial position summary. It remains better in
reference error than all three expanded association variants on 0342.

| Stage | 0342 c=0 | 0342 fitted c | 0039 c=0 | 0039 fitted c |
|---|---:|---:|---:|---:|
| Original pilot | 5.000 | 4.998 | 3.372 | 3.502 |
| Causal prior repair and failed-track exclusion | 2.023 | 1.962 | 0.760 | 0.893 |
| Earlier corrected prototype: also restore the 36-point 0342 suffix | **1.786** | **1.736** | **0.760** | **0.893** |
| Expanded greedy / joint reconstruction | 2.147 | 2.105 | 1.159 | 1.286 |
| Expanded EM MAP reconstruction | 1.949 | 1.897 | 1.159 | 1.286 |

The new variants replace the investigated lane's fragments with expanded
multi-peak satellite tracks; they do not simply append points to the earlier
36-point salvage. In 0342 that changes calibration support from 932 points
in the earlier corrected prototype to 974 (greedy/joint) or 973 (EM).
In 0039 it replaces 58 curved calibration samples with the continuous
88-point primary and 26-point secondary tracks, increasing full-scan support
from 854 to 910. Changed memberships and fragment grouping change the joint
compromise among position, satellite phase, fragment constants and robust
weights. The influence diagnostics below investigate that sensitivity; they
do not establish that every added identity is wrong. See the
[earlier intervention report](../2026_10_18_ds23_adaptive_failures/README.md)
for the 36-point salvage gates and its independently scaled boundary check.

## What was passed into the position estimator

The position estimator uses measured GLRT CFO samples. Polynomials determine
membership; fitted polynomial values and satellite residual corrections are
not substituted for observations. Each reconstructed CFO is checked to differ
from its stored GLRT measurement by an **integer alias period only**.

Unchanged curved tracks from the full scan remain in the fit. Original curved
fragments in the investigated lane are replaced when at least half their
observations lie in the requested interval. This retains the earlier 0342
CH2 track ending at 63.275 s, rather than dropping its whole 31–63 s support.
New winners reuse their original observation identities, and secondary peaks
get stable distinct identities. Duplicate physical observation ownership is
rejected. Every c=0/fitted-c pair has matching measurements, aliases and
satellite nominations.

| Scan | Matched control curved points | Greedy / joint curved points | EM MAP curved points |
|---|---:|---:|---:|
| 0342 | 896 | 974 | 973 |
| 0039 | 854 | 910 | 910 |

These are **curved points used for position calibration**, not all GLRT marks
or all associated linear extensions. The linear-track policy is unchanged:
linear fragments do not vote on calibration. In 0039 the original two curved
fragments contribute 58 calibration points; replacing them by the 88-point
track and adding the 26-point secondary curve adds 56 calibration samples.

The three original association outputs are conditional RF-derived inputs from
the previous experiment. No hand-written satellite whitelist is introduced.
During target refresh, every satellite in the same 1,539/1,488-entry causal
catalogue is screened again, with unchanged candidate and numerical budgets.
The unaffected full-scan track nominations remain the original RF-discovery
outputs, as noted above. This distinction matters when comparing these results
with a completely fresh full-pipeline run.

## Position search and nuisance model

Each initial position fit starts at local east/north **(0,0)** in the existing
25×25 km box centered on **37.906, −122.545**. Both coordinates are bounded
to ±12.5 km. No reference coordinate selects a start, association or result.
Subsequent association refresh starts from the preceding inferred endpoint.
This is a bounded local solve from the regional center, not a multistart
proof of a global optimum over the entire box.

The estimator jointly refits the existing receiver/band frequency offsets,
receiver linear drifts and band contrasts, receiver smooth terms, satellite
phase, eligible causal orbital uncertainty modes, and fragment constants.
Gaussian nuisance integration and grouped robust noise follow the existing
pipeline. All parameters are reprofiled as position changes; receiver
calibration is no longer frozen at the association-prototype estimate.

There are five phase-reference refresh rounds, each allowing up to 48 accepted
Gauss–Newton iterations. Absolute zero-centered priors remain absolute after
relinearization. The phase widths use only latest/earlier **pre-observation**
TLE disagreement and age, with a minimum 1 s genuine epoch separation for the
earlier set. Both epoch and collection causality are preserved by the existing
input adapter. No following TLE is loaded.

Noise estimates remain radio-only. Existing observations retain their
previous per-observation scales. New secondary observations use the same
frozen margin-based noise rule, without fitting their uncertainty from
satellite residuals. Each receiver/band offset and drift is scan-specific;
nothing is learned jointly across the two scans.

![Accepted position iterations from the regional center](position_paths.png)

Lines show accepted position iterations within each phase expansion. The
nuisance coefficients are re-estimated at every evaluated position. Target
associations are refreshed between the subsequent batches, rather than
continuously after every numerical trial step. Reference stars are added only
by the reporting tool after fitting.

## Shared satellite scale ablation

The second position model adds one Gaussian Doppler-scale parameter per
repaired RF-nominated satellite family, shared with that family's other tracks.
Its prior standard deviation is 0.005, centered at zero. This is distinct from
the RF-dependent **constant** coefficient c. The existing LNB drift parameters
remain shared receiver terms; no independent linear correction is added to
each polynomial piece.

Unlike the bounded local association fitter, the integrated position model
uses an untruncated Gaussian scale prior. All posterior scale means in these
runs remain within ±0.005, but the two prior integrations are not identical.
The ablation is matched within the position experiment and is not presented
as an exact implementation of the bounded association likelihood.

| Approach with added satellite scale | 0342, c=0 | 0342, fitted c | 0039, c=0 | 0039, fitted c |
|---|---:|---:|---:|---:|
| Matched control | 1.997 | 1.927 | 1.085 | 1.202 |
| Greedy graph repair | 2.241 | 2.174 | 1.604 | 1.664 |
| Joint path selection | 2.241 | 2.174 | 1.604 | 1.664 |
| Satellite EM MAP | 2.111 | 2.061 | 1.604 | 1.664 |

![Same-observation satellite-scale ablation](satellite_scale_ablation.png)

For example, in the 0039 greedy c=0 fit, adding scale reduces full-scan RMS
from 62.594 to 62.571 Hz on the **same 910 observations**, while error grows
from 1.159 to 1.604 km. A better in-sample frequency residual is therefore
not evidence of better localization.

The added-scale model's penalized RF score is worse by approximately 4.2–5.1
for the repaired c=0 variants. Both c arms prefer the native model in every
case. Choosing the lower RF marginal score would therefore select the
no-extra-scale results in the main table, without consulting position error.

The persistent bias is mainly eastward:

![Endpoint offsets relative to the reference](position_offsets.png)

## Conservative EM policy

The previous association experiment also provided a subset requiring
conditional assignment posterior ≥0.8. Passing that subset into the same
native position estimator gives:

| EM reporting policy | 0342, c=0 | 0342, fitted c | 0039, c=0 | 0039, fitted c |
|---|---:|---:|---:|---:|
| MAP | 1.949 | 1.897 | 1.159 | 1.286 |
| Posterior ≥0.8 | 1.934 | 1.881 | 1.043 | 1.171 |

The conservative policy uses 970 and 907 curved calibration points. It helps
these two cases relative to MAP, but it still does not beat the matched 0039
control. These are conditional association probabilities under the supplied
model, not calibrated identity confidence. This policy is a pre-existing
association output, not a threshold selected by searching GPS error. Its
position propagation is a fixed-association control; the MAP variants are
the ones with the explicit target-refresh runs.

## Added-track influence diagnostics

To investigate the increased error, each added greedy track was masked in
turn while preserving the full augmented nuisance design, prior support and
remaining data. These runs are diagnostics, **not a GPS-based rejection rule**.
Raw scores across different data masks are not ranked as model evidence.

| Scan | All repaired tracks | Mask added track 0 | Mask added track 1 | Mask both |
|---|---:|---:|---:|---:|
| 0342, c=0 | 2.147 | 2.308 | 1.993 | 2.023 |
| 0342, fitted c | 2.105 | 2.255 | 1.948 | 1.961 |
| 0039, c=0 | 1.159 | 0.891 | 0.963 | 0.773 |
| 0039, fitted c | 1.286 | 1.054 | 1.101 | 0.940 |

In 0342, track 0 is 65504 and track 1 is 68214. The first helps position under
this model while the second pulls it farther from the reference. EM differs
from greedy near the handover and retains 43/34 rather than 42/36 samples,
which is consistent with ambiguous ownership having an outsized effect. That
is an interpretation of the influence result, not proof that the 68214
identity or every excluded boundary point is wrong.

In 0039, track 0 is the recovered 59569 main curve and track 1 is the additional
66478 secondary curve. Masking either reduces error, but **neither alone
restores the matched 0.760 km result**. It is not explained solely by the new
secondary association. Joining the main fragments also changes their shared
constant/noise constraints, and the added data impose a different compromise
with the phase/orbit/hardware priors. These tests do not identify a unique
physical root cause or justify discarding a well-supported curve based on GPS.

![Added-track influence](added_track_influence.png)

Masking both added tracks is not exactly the original matched control in
0039, because its original 58 calibration observations were replaced. The
augmented orbital-support design is also deliberately retained in these
diagnostics. The masks therefore measure influence within the repaired
model, rather than pretending to reproduce the original data/model exactly.

## Integration checks and limitations

An initial adapter incorrectly selected new aliases against zero receiver
offset, even though the existing RX1 gauge in 0342 is close to half an alias
period. Its new-track residuals were about 200 kHz and the robust likelihood
almost ignored them. This was diagnosed from RF residuals/weights, not GPS,
before reporting valid position comparisons. Corrected alias choices use the
receiver gauge inferred from other tracks at the declared regional center.
No continuous fitted correction is applied to a measured CFO.

The invalid preliminary runs are retained under `alias_gauge_diagnostic/`
for audit and excluded from every table and figure. In valid runs the added
0342 tracks have approximately 119–122 Hz RMS and normal robust precision,
so the reported small position shifts do not come from silently ignoring them.

Six new tests cover radio-only secondary noise, the half-period gauge
regression, targeted replacement, raw CFO preservation, absolute phase/scale
linearization and coefficient-block indexing. **All 66 tests in the targeted
regression selection pass**, and Ruff passes. The reporter additionally audits
matching c-arm observations/aliases/nominations, convergence, finite box
bounds, genuine earlier phase epochs, scale means and added-track weights.

There are 64 primary/control position records and 12 additional influence
fits. The three methods share parts of their candidate/position machinery and
often choose the same observations; identical errors are expected when their
actual inputs coincide. No independent performance estimate or uncertainty
coverage follows from rerunning those identical inputs.

## Recommendation

Keep the graph construction repair: it resolves the demonstrated false bridge
and lost continuation. For position estimation, retain the existing joint
nuisance model and let penalized RF evidence decide whether an extra satellite
correction is warranted. On these scans it is not warranted. EM's ambiguity
handling is worth retaining, but these two scans do not establish an overall
localization advantage.

The remaining problem is the relationship between orbit/phase/hardware
uncertainty and geometry, rather than missing polynomial points alone. The
influence diagnostics motivate independent family-consistency tests and
better-calibrated nuisance priors; they do not support selecting tracks or
hyperparameters using position error. A fresh full-lane discovery and broader
dataset position comparison remains a separate evaluation.

## Artifacts and reproduction

- `position_comparison.csv`: every evaluated error, frequency RMS, point count,
  model, c arm and fixed/refreshed stage.
- `refresh_checks.json`: target membership convergence and fixed/refreshed shifts.
- `influence_evaluation.json`: added-track influence errors.
- `historical_pilot_comparison.json`: explicitly unmatched pilot errors.
- `validation.json`: input/output/source hashes and numerical audits.
- Per-case/method JSON files contain position iterations, fitted nuisance
  parameters, measured input tracks, alias choices, phase-prior provenance and
  the target refresh histories.

Run `tools/propagate_ds23_arc_positions.py` with `--case DS23-0342|DS23-0039`,
`--method baseline|greedy_graph_repair|joint_paths|satellite_EM`,
`--arm c0|fitted_c` and `--model native|shared_scale`. Use the existing
`PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python`
environment. Run once without flags for fixed propagation, then add `--refresh`
for each repair method. `--confident` provides the fixed conservative EM
control, and `--influence` provides the greedy added-track masks.

Finally run `tools/report_ds23_arc_positions.py`. Only that reporting step
accesses the evaluation coordinate; fitting outputs do not contain position
error or use it for any decision. All data are existing frozen local GLRT and
causal TLE artifacts. No new RF collection, future TLE access, production
change or remote publication is part of this experiment.
