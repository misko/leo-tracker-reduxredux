# Fixed-position prediction outside the 24-scan fitting pools

The N24 positions retain promising geographic errors, but do not predict
outside scans as well as a fixed equal mixture of three N8 positions. The
mixture wins on 13/15 target scans and in every dataset's aggregate. This
reinforces the distinction between a useful point estimate and a calibrated
measurement model; it does not establish blind sub-km accuracy.

| Dataset | Earlier N24 reference error | N24 − center predictive log score | N24 − N8 mixture predictive log score |
|---|---:|---:|---:|
| DS7 | 387.5 m | +44.450 | −187.062 |
| DS8 | 389.8 m | −40.682 | −148.135 |
| DS9 | 107.2 m | +56.523 | −109.797 |

Positive log-score differences favor N24. These predictive scores are natural
log units, not geographic errors. Earlier errors come from the
[scan-budget experiment](../2026_09_29_scan_budget/README.md); no new locations
were fitted here. The configured center itself is 809.0 m from the inherited
reference, so merely crossing 1 km is a weak success criterion at this site.

![Per-target predictive differences](prediction.png)

## Frozen comparison

The full-ready authority contains 88/65/105 scans for DS7/DS8/DS9. Excluding
each dataset's corresponding 24-scan source pool leaves 64/41/81 candidates.
We sorted those by capture-start timestamp and session ID, then selected
five fixed order statistics: floor(j*(N−1)/4), j=0..4. The [manifest](manifest.json)
was written before scoring. No target score, reference error or quality rank
entered selection; there were no target substitutions.

Each of the 15 targets was scored at five fixed positions: configured center,
N24, and three N8 fits. All source fits were qualified and the three disjoint
N8 sets together use the same 24 source scans as N24. We retained the q020
candidate/background likelihood and integrated each complete scan over one
shared unknown timing offset with a uniform prior on [−5,+5] s. Neither
location nor timing was refitted on target data.

For each target, the N8 comparator is logsumexp of its three timing-integrated
log densities minus log(3). This averages densities with fixed equal weights;
it does not select the best component using the target. Reported sums are
sums of per-scan predictive log scores. They are not the joint predictive
density of one shared uncertain location across all five targets. The broader
mixture can accommodate variation that one point estimate cannot; its win
does not imply that any one N8 geographic estimate is better.

## Results and checks

Across 865 tracks and 40,485 observations, N24 beats center on 9/15 scans,
with a total +60.291 log-score difference. It beats the N8 mixture on only
2/15, with a total −444.993 difference. See the [full table](TABLE.md) and
[machine-readable summary](summary.json) for every target.

All 75 integrations passed the 16/32-node-per-bank-interval convergence gate
of 0.01 log units; maximum discrepancy was 0.006381. No refinement was needed.
The maximum difference from the scalar likelihood oracle was 2.19e−11.
All 15 subprocesses completed successfully, each below 39 seconds, with
three workers and a frozen 180-second cap. Summed numerical runtime was
442.2 seconds; wall time was shorter because runs overlapped.

Four selection/mixture tests passed, as did Ruff. Input bytes and source
bindings were checked before and after scoring. The
[prior-seal audit](prior-seal-audit.json) matches the inherited N24/N8 outputs
and target artifacts against their earlier evidence seals. Raw per-target
results, subprocess receipts, protocol, code and digest seal accompany this
report. No production analyzer, golden fixture or RF collection changed.

## Interpretation and next experiment

Pooling more scans improves reference-relative point estimates, while both
the earlier interleaved holdout and this outside-pool test favor more flexible
predictions. A plausible explanation is residual scan-dependent model error;
this experiment does not identify its physical cause. Candidate ambiguity,
timing, orbital errors and waveform residuals remain possible contributors.

The next useful bounded experiment is to diagnose which candidate/track
groups account for the predictive losses, then test a physically constrained
shared-error model on a separately frozen split. Avoid unconstrained per-track
slopes: earlier information tests showed they can absorb position information.
Use predictive scores and geographic errors together before promoting a model.

These targets were excluded from the current source fits, but were explored
in earlier corpus research. They are not a fresh blind holdout. Retained
candidate banks remain site-conditioned; the timing prior has no external UTC
calibration. The geographic reference is inherited, exposed and unsurveyed.
The source pools span roughly 8–13 hours, not 24 consecutive low-latency scans.
Independent site/reference and timing evidence are still needed to establish
general sub-km performance.

## Reproduction

The outputs are local research artifacts. Generation uses exclusive output
creation to avoid overwriting evidence; archive a completed run before a fresh
reproduction rather than rerunning these commands into the existing folder.

```bash
python3 -m unittest discover -s reports/2026_09_29_out_of_pool -v
python3 reports/2026_09_29_out_of_pool/study.py prepare
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_out_of_pool/study.py batch
python3 reports/2026_09_29_out_of_pool/summarize.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with matplotlib python reports/2026_09_29_out_of_pool/plot.py
```
