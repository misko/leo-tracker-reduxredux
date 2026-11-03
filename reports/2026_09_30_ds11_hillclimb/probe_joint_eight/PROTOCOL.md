# Eight-frame joint frequency comparison

Retain all six probe-coexistence pairs and saved20ms excerpts. Use frames0–7
for each frozen candidate, advancing epochs by the exact5MS/s /750Hz frame
period. Reuse the common interior-sample training/held masks per frame: fitting
symbols22–221, evaluation222–301. Require every frame to provide at least512
training and256 held samples. Keep all cases; missing support makes a case
unavailable rather than authorizing replacement or fewer frames.

Pool frames noncoherently: fit independent complex gains per frame/carrier and
two frequency residuals shared across frames. Sum raw fitting squared errors
and normalize by total fitting energy. Held NMSE is likewise total squared
error divided by total held energy, not an unweighted mean of frame NMSEs.
Report the individual frame NMSEs too. All three arms reconstruct both signals.

Compare cached frequencies, separately refined frequencies and jointly refined
frequencies. Reuse the prior25Hz grid over±1500Hz, bounded single refinements,
two joint starts (zero and separate),80iterations/120evaluations, interior and
derivative qualification, and training-score selection. Record selections
before held scoring. Do not refine epochs or change aliases. Separate-boundary
fits remain flagged and make the comparison unusable.

Advancement requires all six comparisons usable, at least5/6 joint wins
against cached AND at least5/6 against separate, plus positive mean and median
paired gains against BOTH. This is a new stronger engineering gate, frozen
before this experiment; preserve the earlier single-frame results and gate.
Do not tune on the outcomes or propagate corrections to positions here.

One worker capped at120seconds, one BLAS thread, nice19, no retries. Bind all
prior sources, excerpts, code and tests. No new IQ reads beyond saved excerpts,
RF collection, orbit update, geographic scoring or position fit. Synthetic
tests verify common frequency recovery with independent frame gains, analytic
derivatives, and energy-weighted aggregation before data execution.
