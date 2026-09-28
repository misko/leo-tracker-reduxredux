# Whole-track noise-scale pilot on DS7/DS8/DS9

Use the first chronological recording from each existing DS7/DS8/DS9 panel,
without replacing any result or using geographic error to select inputs.
Freeze two new arms before fitting: a track-level mixture of Student-t(4) scales
100 and 1,000 Hz with prior weights 0.9 and 0.1; and a 1,000 Hz-only ablation.
The tenfold broad scale tests substantial excess residual scatter. These fixed
values are a coarse hypothesis, not estimated hardware noise or tuned optima.
Replay the historical 100 Hz baseline at its sealed solution. No baseline
refit is needed: the single-scale limit must reproduce its training and held
scores, and both new arms use the original three position/timing starts.

Each track has one latent scale shared across all its observations and one
latent candidate. Profile the stationary offset separately for each candidate
and scale using the original weak offset penalty. Sum both discrete dimensions
with normalized scale priors and the original full-catalogue normalization.
Training-only posterior weights and offsets predict held observations. This
retains the baseline's penalized profile likelihood; it is not a fully integrated
offset marginal likelihood or a new proof of satellite association. No track is
dropped. A broad component allows lower influence for poorly explained tracks;
it cannot by itself establish whether scatter comes from noise or a wrong track.

Retain all original inputs, shortlist nominees, visit masks, geographic origin,
position bounds ±12 km and timing bounds ±5 s. The unchanged 100 Hz shortlist
may miss nominees preferred by the broad model; this pilot is conditional on
the frozen banks and does not certify broad-model candidate completeness.

For both arms, start east/north at zero and timing at 0, -2, +2 s. L-BFGS-B uses
maxiter100, maxfun180, ftol1e-10, gtol1e-5 and maxls30. Retain every start and
select highest training score among successful starts. Report estimates even
if unqualified. Qualification requires success, no bound within 1e-3, and max
absolute coordinate gradient <=0.01. No selection by held or geographic score.
Report original baseline qualification separately from its additional replayed
gradient screen. Fit mixture then broad-only under a single 240-second cap per
record, 4 GiB, one thread, nice19; preserve any completed arm and timeout. No
retry or cap extension. At most two records run concurrently.

Seal terminal outputs before reading bound pose authorities. Report all three
planned records, per-arm failures, geographic errors, held-score changes,
training-fitted broad responsibilities and start sensitivity. Compare the
mixture with broad-only to distinguish adaptive track weighting from simply
changing every track's scale. These three exposed, unsurveyed same-site records
are a numerical/model pilot, not a panel median or generalization result.
Promotion requires subsequent frozen-panel tests; a pilot improvement alone
does not satisfy the sub-kilometer objective. No new RF, IQ or propagation.
