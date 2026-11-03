# Ranked waveform corrections: completed geographic test

Reprocessing the frozen high-influence queue produced larger position changes,
but **no consistent geographic improvement**:4/9 panels improved and5 worsened.
The number below1km remained2/9. Keep the cached operational baseline; do not
promote these corrections or expand reprocessing solely on this result.

| Dataset | Cached median error m | Earlier budget median m | Ranked budget median m | Ranked improves panels |
|---|---:|---:|---:|---:|
| DS7 | 2023.56 | 2024.27 | 2030.49 | 1/3 |
| DS8 | 1721.07 | 1722.84 | 1705.86 | 1/3 |
| DS9 | 876.13 | 875.81 | 825.75 | 2/3 |

Errors refer to the inherited exposed, unsurveyed reference. They are conditional
research results, not independently verified positioning accuracy.

![Cached, earlier-budget and ranked-budget geographic results](comparison.png)

The largest improvement was DS9 early,639.50→539.77m. Its held log score nevertheless
worsened by0.253 nats under the corrected training posterior. DS9 middle improved
876.13→825.75m while its held score worsened3.845 nats. Geographic and predictive
metrics must remain separate; neither was used to select corrections or starts.

## Exactly what ran

All72 observations from the [frozen influence queue](../2026_09_29_observation_influence/queue.json)
were bound back to their original manifests, public tracks and candidates, then
read through the public read-only IQ port. None was replaced or excluded. These
are29 tracks in21 recordings and72 distinct source visits, with eight corrections
per eight-scan panel. This is the same number of observations as the earlier
budget, not a claim of identical extraction time or track diversity.

Each20ms excerpt supplied eight complete frames. The long-pilot estimator fits
one residual frequency from symbols22–221, using independent frame/carrier gains,
the corrected deterministic upconversion phase, and fixed±1500Hz bounds. All72
fits returned; none hit a bound. Median absolute native correction was22.71Hz,
maximum411.76Hz. Later-pilot prediction improved in46/72 excerpts; all corrections,
including those that worsened this diagnostic, entered the geographic test.

| Dataset | Pilot prediction improved | Median absolute correction Hz | Maximum absolute correction Hz |
|---|---:|---:|---:|
| DS7 | 16/24 | 28.95 | 411.76 |
| DS8 | 17/24 | 15.80 | 255.29 |
| DS9 | 13/24 | 27.06 | 309.20 |

The auxiliary pilot score uses symbols222–301 within these training visits.
Those are held pilot symbols, not the localization model's held visits, and
were never a correction-selection gate.

Native residuals were scaled by11.2e9/actual_RF and added to the existing
canonical dealiased observations. Integer alias mappings were verified. The
original4,328 tracks,198,806 observations, candidate banks and masks remain in
the model; every held observation is unchanged. Only72/119,673 training values
(0.0602%) changed. No correction was propagated to an unmeasured visit, and no
frame-jackknife weighting was used.

## Geographic checks and limits

All nine geographic commands exited0. Both arms used the same three starts and
train-only selection. There were53 qualified starts out of54; the unchanged
cached DS7-late middle start again returned an abnormal optimizer status and
was retained as unqualified. All18 selected fits passed independent gradient
checks. Maximum audit discrepancy was0.0000801, below0.02. Source training and
per-track held scores were replayed before fitting.

Held log scores improved in4/9 panels. Evaluating the original measurement model
at each corrected location/timing vector also improved in4/9. [TABLE.md](TABLE.md)
contains every panel's reference error, movement and both held-score differences.

Maximum movement was107.67m, compared with17.71m under the earlier budget.
The ranking therefore selected observations capable of moving the solution,
but movement did not translate into reliable error reduction. Summing the local
response vectors also did not reliably predict the finite combined correction:
vector discrepancies range2.74–165.50m. The prior sensitivity validation used
±10Hz on one observation at a time; actual corrections reach412Hz and modify
eight observations simultaneously. These are materially different perturbations.
Candidate/posterior changes and model nonlinearity can matter; this comparison
does not by itself assign the discrepancy to a particular cause.

The model was fitted locally around existing solutions, not globally certified.
The panels and reference have been exposed, and the raw-frequency refinements
lack external Doppler truth. Higher pilot coherence or greater position influence
does not establish that a correction has the right physical interpretation.

## Decision

Retain the cached baseline and treat influence ranking as a budget-allocation
diagnostic, not a rule for automatically changing influential observations.
Do not tune correction signs, shrinkage or quality cutoffs against these held
or geographic outcomes. Before another waveform expansion, use the now-available
ranked IQ to distinguish whether inconsistent corrections arise from within-
excerpt estimator effects or from the model's interpretation of the observations.
A further experiment needs a frozen physical or measurement-model hypothesis,
not a larger budget justified only by influence.

Consistent sub-kilometer accuracy remains unresolved. The isolated DS9 gains
do not establish a generally improved method.

## Evidence and execution

- [PROTOCOL.md](PROTOCOL.md), [plan.json](plan.json): frozen methods and exact selections.
- [inventory.json](inventory.json): all72 public-port bindings and raw-file hashes.
- [measurements.json](measurements.json): all residuals, boundary flags, per-frame
  pilot scores, summaries and dependencies.
- [summary.json](summary.json), [TABLE.md](TABLE.md): complete geographic outcomes,
  earlier-budget comparison and predicted-versus-observed movement errors.
- `DS7_early_8.json` through `DS9_late_8.json`: every applied correction, all fit
  starts, selected fits, held scores, audits and hashes.
- [extraction_receipts.json](extraction_receipts.json), [receipts.json](receipts.json):
  bounded extraction and geographic execution records.
- `prepare.py`, `extract.py`, `measure.py`, `run.py`, `launch.py`, `summarize.py`,
  `test_run.py`: reproduction and tests.

Extraction completed within the four120-second invocation budget, checkpointing
19,47,63 and72 entries respectively; the first three exited124 at their caps,
and the fourth exited0. Numerical waveform estimation finished within120seconds.
Geographic fits took210.70seconds total, maximum26.51seconds per panel, each below
its60-second cap. Two geographic helper tests and four inherited waveform tests
pass; Ruff checks pass. Source and result hashes are verified. No new RF was
collected, published contracts changed, or production estimator deployed. Reports
and evidence are local; this experiment did not push to remote main.
