# Shared position across DS7, DS8 and DS9

Freeze the existing first-eight chronological panels, 24 recordings in total.
Reuse the exact zero-slope baseline observations, causal candidate banks,
Student-t(4,100 Hz) likelihood, stationary-offset profiling, full catalogue
normalization, visibility and whole-visit training/held masks. No waveform
correction from the preceding pilot experiments is introduced. No new RF, IQ,
catalogue propagation, geographic prior penalty or reference-driven selection.

Fit four units: all 24 records, and three donor fits that each exclude one
entire dataset and use the other 16. Each fits one horizontal position plus
one timing offset per included recording. Bounds remain ±12 km and ±5 seconds.
The inherited coordinate center is exposed DS6 information, not a new spatial
penalty. This is already exposed, unsurveyed same-site evidence, not new-site
generalization or a calibrated resolution claim.

Initialize timings from the included datasets' qualified polished zero-slope
eight-record fits. Position starts are each included dataset's own fitted
position: three starts for all24, two for each donor fit. Excluded fit locations
and timings cannot enter donor starts or fitting. This is a local multi-start
comparison, not a global search. Replay each included source baseline score
within absolute 1e-7 before optimization.

Each start is a separate 180-second, 4-GiB, single-thread, nice19 job; at most
two numerical jobs overlap. L-BFGS-B maxiter140/maxfun200/ftol1e-12/gtol1e-6/
maxls30. Persist every returned start and terminal failure. Select maximum
training score among successful starts, never by held or geographic outcome.
Strict qualification also requires no coordinate within 1e-3 of a bound and
maximum absolute coordinate score gradient <=.01. Do not replace a selected
unqualified point with another start selected by qualification. No retries,
deadline extensions, numerical polishing or replacement records in this trial.

After all starts for a unit terminate and are sealed, evaluate its included
records' held full-mixture scores at the selected point. Each source scoring
job is capped at 90 seconds/4 GiB. For each successful donor fit, freeze its
position and fit only the eight excluded-record timings, using that dataset's
training observations and fixed starts of 0,-2,+2 seconds. Per-track stationary
offsets and candidate weights may adapt on excluded training observations, but
position cannot. This is transfer with local nuisance adaptation, not a wholly
unseen or zero-shot predictive score. Held observations never optimize anything.

Each target-timing start has a separate 120-second/4-GiB cap, maxiter100/maxfun180/
ftol1e-12/gtol1e-6/maxls30, same qualification and training-only selection rules.
Seal these fits before scoring held target observations (90 seconds/4 GiB).
Report all eight target held differences versus the original eight-record fit,
including losses. A source failure leaves its transfer unavailable.

Only after fitting/held evidence is sealed, read bound pose companions for
geographic scoring. Report all24 as one 24-record budget, donor fits as 16-record
budgets, original panels as eight-record budgets; never relabel the pooled result
as independent DS7/DS8/DS9 performance. Include coordinate-origin error, all
start outcomes, coverage, gradient/boundary qualification and paired held changes.
No sub-km or generalization claim based solely on optimizer convergence, pooled
data volume, or an already close inherited coordinate origin.
