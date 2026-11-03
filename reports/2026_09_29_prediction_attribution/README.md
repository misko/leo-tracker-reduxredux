# Where the fixed N24 position loses predictive score

This diagnostic explains the earlier outside-pool prediction comparison; it
does not fit a new location or demonstrate an additional geographic gain.
All 15 targets, their input bytes, and the N24/N8 source positions are inherited
unchanged from [out_of_pool](../2026_09_29_out_of_pool/README.md).

The completed attribution shows that poorer track fit accounts for the loss;
the timing/component concentration term favors N24 slightly. Losses occur
on both receivers and across multiple RF channels. This is evidence against
treating the problem as a single bad receiver or simply rejecting more tracks.
It does not isolate the physical cause or rule out receiver geometry effects.

| Dataset | N24 − N8 mixture log score | Track contribution | KL contribution |
|---|---:|---:|---:|
| DS7 | −187.054 | −192.872 | +5.819 |
| DS8 | −148.133 | −154.193 | +6.060 |
| DS9 | −109.798 | −115.031 | +5.234 |

Values are natural-log units, not metres. The finer integration used here
differs slightly from the earlier report's primary 16-node scores; conclusions
are unchanged. Rounded table columns may differ by 0.001 when added.

![Score attribution](attribution.png)

Across 865 tracks, 475 have negative contributions. RX0 contributes −237.287
and RX1 −224.810, before the separate +17.112 KL contribution. Gross negative
track contributions total 1483.833, partly offset by positive contributions.
The 20 largest losses account for 27.2% of gross negative contribution, so the
problem is not confined to a handful of outliers. Of the 475 losing tracks,
442 retain signal probability above 0.99 under both arms; all top 20 have
probability effectively one. Those probabilities are model-conditional and
must not be mistaken for externally validated satellite confidence.

The next bounded diagnostic should resolve physical candidate posteriors for
the same frozen comparison: distinguish satellite-assignment changes from
residual Doppler mismatch at a stable assignment. That distinction can guide
a subsequent constrained correction. Do not immediately add unconstrained
track slopes or increase rejection: earlier slope experiments can absorb
location information, and these losses predominantly involve retained signal
tracks. No improved point estimate is claimed by this diagnostic.

## Method

For each target we evaluate the same full-track q020 likelihood at the N24
position and the three fixed N8 positions. Unknown timing is shared across
tracks within each scan and integrated uniformly over [−5,+5] seconds. N8
positions have equal prior weights. For latent timing/component state z:

```
log predictive density = sum over tracks E_posterior[log track likelihood]
                         − KL(posterior latent state || prior latent state)
```

This identity separates each track's expected log-likelihood contribution
from the timing/component concentration penalty. Its differences reconstruct
the N24-versus-mixture prediction difference exactly at the evaluated
quadrature resolution. There is no order-dependent sequential allocation.

The track contributions are posterior-dependent diagnostics, not causal
effects of removing tracks. Both arms use different latent posteriors.
Grouped values by receiver or RF exclude the separately reported KL term.
Signal responsibilities are probabilities within the inherited retained-bank
model; they do not establish satellite identity or trustworthy absolute
confidence. Track rankings are reported only after scoring and are not used
to remove observations, choose a location, or tune the model.

## Numerical protocol and evidence

The original 16/32-node calculations replay the previous run's corresponding
whole-scan integrals to 1e-7. Each new track-wise implementation is also checked
against the scalar likelihood at five timing offsets and four positions per
target. Every decomposition must reconstruct evidence to 1e-7.

The stricter track-attribution stability gate failed initially for DS7_1,
DS7_3 and DS9_4. Original results remain intact. The documented
[numerical amendment](REFINEMENT.md) repeats those targets only at 64/128 nodes,
without changing the statistical model or the 0.01 stability threshold.
No aggregate is allowed until every target qualifies. Original and refinement
subprocesses each have a 180-second cap and at most three concurrent workers.

All 15 targets qualified after the three refinements. Maximum scalar replay
error was 1.46e−11; identical-node replay against the prior report differed by
at most 7.28e−12. Refined 64/128-node track differences were below 2.02e−9 and
their evidence differed from the original 32-node values by at most 5.62e−9.
All 18 subprocesses exited successfully; the longest took 75.1 seconds and
summed numerical runtime was 521.3 seconds. The two unit tests and Ruff passed.
Original failures remain present and marked unqualified, with separate
refined artifacts selected only by the documented numerical gate.

The [frozen manifest](manifest.json) binds source data, prior results, protocol
and code. Per-target JSON contains track metadata, both resolutions of the
decomposition, signal probabilities, replay errors and qualification status.
Subprocess receipts record failures and exits. The [full table](TABLE.md) and
[summary](summary.json) contain all qualified contributions, including the
largest negative tracks. The original protocol is [here](PROTOCOL.md).

Two mathematical tests cover explicit-density reconstruction, constant
likelihoods, large negative log values, and track permutation. Runtime scalar
and prior-evidence replay tests cover the real 15-scan corpus. The numerical
work uses existing exported artifacts only; no RF, production code, golden
fixture, or QNAP path is modified.

## Limits

These targets were excluded from the N24/N8 fits but were explored in earlier
research. Candidate banks remain site-conditioned; neither an externally
calibrated UTC prior nor independent satellite truth is supplied. The earlier
388/390/107 m N24 errors refer to an inherited, exposed, unsurveyed geographic
reference. This attribution cannot prove general sub-km performance or isolate
a physical cause of the residuals by itself.

## Reproduction

Commands create evidence files exclusively. Use a fresh archived-run context;
do not overwrite the completed run's artifacts.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_prediction_attribution -v
python3 reports/2026_09_29_prediction_attribution/study.py prepare
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_prediction_attribution/study.py batch
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_prediction_attribution/refine.py batch
python3 reports/2026_09_29_prediction_attribution/summarize.py
uv run --no-project --with matplotlib python reports/2026_09_29_prediction_attribution/plot.py
```
