# Paired receiver evidence and partial-arc support

This descriptive development audit uses only the original six calibration
recordings in the frozen receiver-geometry dataset. It does not fit a model or
score the original evaluation four or DS8. Existing eligibility and all retained
windows are preserved, including qualified empty receiver candidate sets.

The observation audit uses candidate counts and fractional detector margins,
without candidate frequencies, residual gates, closest-match selection or
nominee weights. Margins are detector statistics, not calibrated received power.
Count asymmetry is (n1-n0)/(n1+n0), undefined for both empty; mean-mark contrast
requires marks on both receivers. Report missing/nonfinite marks explicitly.
These summaries measure available detector evidence, not satellite presence or
paired physical signals. Do not interpret an absent thresholded detection as a
physical beam entry/exit.

The separate forecast audit uses q=2 sin(10 degrees) times LOS east for each
track/catalog nominee. Remove each trajectory's within-role mean before computing
prior-weighted RMS disagreement among trajectories. This removes constant
receiver offsets and asks whether candidate hypotheses predict different changes
over the same partial arc. Report conditional retained prior normalization,
omitted prior mass, effective nominee count, excursions and secants. A nonzero
result is geometric support, not evidence that the observations follow it.

Keep outcomes and forecasts separate in this stage: no correlation search,
threshold optimization, selected outcome subset or direction claim. Before a
likelihood experiment, review detector-mark semantics and whether materially
weighted candidates have distinguishable temporal geometry.

Verify frequency/outcome perturbation independence with component tests; reject
malformed receiver and forecast structures explicitly. Bound each export to
60 seconds, one numerical thread and 1 GiB. Bind source, tests, dataset and this
protocol in exclusive launch receipts. Preserve failures. No RF collection,
IQ reprocessing, propagation or QNAP mutation.
