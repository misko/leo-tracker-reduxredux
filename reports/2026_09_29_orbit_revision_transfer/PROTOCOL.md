# Cross-dataset transfer of one orbital-revision coefficient

Freeze before execution. Reuse all 3,983 conditional residual cases and the
checked 24-hour orbit revision from the exact replay. Export its full frequency
delta using the same two-node interpolation and verify each case against the
previous held error, revision slope and RMS. Missing records get a zero direction
and remain in all-population scoring.

Model prediction is baseline plus beta*(older minus baseline), beta in [-1,1].
One common coefficient is fitted using training observations of two datasets;
evaluate its held observations on the excluded third dataset. Repeat for each
DS. This is cross-dataset development transfer, not chronological forecasting or
independent sites. Center residuals and revision directions using each track's
training mean. Optimize Student-t4 loss at 100-Hz scale, averaging observations
within track, tracks within dataset and the two donor datasets equally.

Search a fixed 81-point grid on [-1,1], include endpoints and zero, refine every
interior grid-local minimum using bounded scalar minimization. Select lowest
training loss; no held or reference-position selection. Controls beta=0, beta=1
(older orbit) and beta=-1 (one full revision extrapolation). Keep missing and
unchanged cases; report all and changed subsets and all nine target panels.
No per-track, per-satellite or target-trained coefficient. No geographic fit.

If predictive transfer improves consistently, evaluate position-information
retention for this one shared direction before geographic promotion. Otherwise
stop this coefficient model. Prior location/association fitting conditions every
residual; a GP revision direction is not precision orbit truth or a measured bias.
No new RF/download or production edits. Export and fitting each capped at 120 s,
one numerical thread; archive access uses only the read-only reader.
