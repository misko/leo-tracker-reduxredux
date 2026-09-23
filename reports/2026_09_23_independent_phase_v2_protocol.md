# Acquired-only phase comparison: frozen revision 2 protocol

This revision follows the [failed training gate](2026_09_23_independent_phase_training_audit.md).
It preserves the same 15 training / 12 random held dwells and does not open the
19 originally reserved observations or long-cohort validation/test recordings.
No chronological holdout or new RF acquisition is used.

## Measurement and training

Use only each observation's original acquired CFO as the raw-sample NCO seed.
Do not choose among refined/dealiased seeds or seed expansions. Keep the original
integer frame timing and 24 opportunities in six groups. Frame eligibility is
the existing calibration-even support policy. Calibration uses even symbols in
groups 0, 3, 5; responses use odd symbols in groups 1, 2, 4. Odd boundary values
remain responses; no odd coherence filtering or outlier removal is allowed.

Each fold samples every other 4.4 µs symbol, giving a fixed-symbol-matrix
frequency period A = 1/(2 × 4.4 µs) = 113,636.364 Hz. For the **15 training
dwells only**, put the acquired branch's eligible even mean m in the archived
GLRT gauge g using k = round((g − m)/A), and normalize (m + kA) by the bound RF
scale. This is a conditional training coordinate, not physical alias resolution.
If a training dwell lacks even support, abort model fitting rather than silently
changing the frozen population. The acquired branch has training support in all
15 dwells before this revision is frozen.

Fit the same six models as revision 1: GLRT/phase candidate, GLRT/phase
wrong-time geometry, and GLRT/phase constant frequency rate. Keep the same 880
causal candidates, 398 regional 50 km grid sites, 16 cached finalists per arm,
exact SGP4 reranking, above-horizon training constraint, and one fitted offset
plus linear receiver drift with equal dwell weight. Use actual measurement
times. Wrong-time geometry uses mirror_sum − 2 × dwell_time + frame_time;
receiver nuisance remains in actual time. Embed the selected causal TLE lines
and freeze all numerical inputs, models, measurement/scoring code, and this
protocol before held IQ is opened.

## Held response and endpoint

On each held dwell, extract the **acquired branch only**. Do not read its bound
GLRT CFO, refined CFO, or dealiased CFO to construct the response, choose its
seed, fix an alias, or gate a frame. Source timing, acquired seed, receiver/RF
metadata, and historical track membership are inherited conditions, so this is
not blind source discovery.

For every eligible odd frame, the response is y = RF_scale × odd_absolute_CFO,
without any alias lift. All models receive exactly the same response and frame
mask. Let P = RF_scale × A and let mu be the frozen model's exact prediction.
Score on the circle using the wrapped normal density with fixed sigma = 250 Hz:
sum over integer n of Normal(y − mu + nP; 0, sigma²). Implement its negative log
density using log-sum-exp of the principal residual and its two adjacent images;
the other images are numerically negligible at this fixed P/sigma. Average
frame scores within each dwell, then dwell scores equally. Primary endpoint is
the resulting wrapped estimator-coordinate negative log score. Also report
principal-residual RMS with equal dwell weight, all frame/dwell coverage,
abstentions, odd boundary counts, and per-dwell results. Never persist a
model-selected wrap integer as an observed physical alias.

This density defines a score for the circular estimator output. It is **not a
raw-IQ likelihood**: changing the acquisition NCO also changes tone extraction,
and fold periodicity does not establish raw-IQ branch equivalence. A training-only
audit of acquired and acquired ± A branches across all 15 dwells records support
and measurement differences. That audit does not select a replacement branch,
new threshold, or held variant. Its outcome limits physical interpretation.

Every unsupported held dwell remains an explicit abstention. Do not change
the model, extraction rule, response gauge, sigma, or controls after seeing
held results. Report both candidate arms and all four controls, not a variant
selected by held outcome. Any paired whole-dwell bootstrap is descriptive,
uses seed 20260925 with 10,000 resamples, and does not drive model selection.

## Interpretation and validation gates

A phase candidate must improve over the matched GLRT candidate to show an
incremental estimator benefit; beating affine and wrong-time controls is also
necessary for geometry-specific predictive evidence. Passing those controls
would demonstrate held CFO congruence modulo P on this inherited source arc.
It would not identify the absolute alias, confirm a satellite, establish orbit
velocity, or validate receiver position. Independent multi-arc position and
association checks remain necessary for those claims.

Before opening held IQ, tests must establish: fixed-matrix fold periodicity;
full-symbol non-periodicity at A; acquired-only branch selection; invariance of
responses to changes in held archived GLRT/refined/dealiased CFO; no odd-dependent
eligibility or branch choice; retained odd boundaries; circular score invariance
to integer-period changes of response/prediction; equal dwell weighting and
explicit abstentions; exact propagation at frame times; and correct wrong-time
within-dwell transport. Preserve revision 1 artifacts and code as the failed
training baseline.
