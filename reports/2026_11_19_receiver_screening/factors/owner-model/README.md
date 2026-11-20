# Why matched satellite IDs do not close the v5 position gap

On DS26-0197, lean and v5 assigned the same satellite and integer CFO branch to all 2,607 shared conditional observations. Exact range rate with the lean receiver model still returned 2.975/1.905 km errors with zero/fitted calibration. A compact refit of the v5 receiver-clock, component-offset and causal phase-prior terms on those same samples reduced the errors to 0.802/0.825 km. The archived full v5 errors were 0.528/0.689 km. On DS26-0223, changing the 120 disagreeing owners improved the common-mask lean fit. On DS29-0316 and DS26-0036, changing owners worsened position despite similar or lower CFO residuals. [Sealed positions](predictions.jsonl.gz) · [Per-arm scores](scores.json)

| Recording | Shared / full conditional points | Owner differences on shared points | Lean owners + lean fit (km) | v5 owners + lean fit (km) | v5 owners + compact clock/prior (km) | Original v5 archive (km) |
|---|---:|---:|---:|---:|---:|---:|
| DS26-0197 | 2,607 / 2,678 | 0 | 2.975 / 1.905 | 2.975 / 1.905 | 0.802 / 0.825 | 0.528 / 0.689 |
| DS26-0223 | 2,232 / 2,727 | 120 | 1.225 / 1.040 | 0.241 / 0.583 | 1.075 / 1.110 | 0.823 / 0.758 |
| DS29-0316 | 2,267 / 2,267 | 44 | 1.282 / 1.512 | 1.561 / 1.842 | 5.010 / 5.078 | 1.007 / 1.011 |
| DS26-0036 | 2,253 / 2,253 | 106 | 1.604 / 1.336 | 2.042 / 1.726 | 1.392 / 1.316 | 1.278 / 1.208 |

Zero and fitted calibration are shown in that order. The four common-mask identity and alias combinations had identical point keys, noise weights, original tile and iteration limits. The 9,359 shared aliases agreed exactly, so both alias-swap cells reproduce their corresponding fixed-owner result. The privileged coordinates in the table and plot are forced diagnostic fits. The actual blind lean exact rerun published DS29-0316 and DS26-0036, and withheld DS26-0197 and DS26-0223. The v5 points come from earlier authenticated publications. [Sealed position figure](owner-oracle-position.png) · [PDF](owner-oracle-position.pdf)

The standard roof atlas has six diagnostic cards. The two pairs of identical alias outcomes share cards. Each card shows four withheld attempts, four forced diagnostic coordinates, and the four original v5 series on the same recordings. [Zero-calibration cards](standard-roof/rendered/c0/modifications.pdf) · [Fitted-calibration cards](standard-roof/rendered/fitted_c/modifications.pdf) · [Evidence and chart definitions](standard-roof/figures.json) · [Render seal](standard-roof/rendered/render-lock.json)

## Frequency and support

| Recording | Common v5-owned lean RMS (Hz) | Common compact clock/prior RMS (Hz) | Archived v5 on identical points (Hz) |
|---|---:|---:|---:|
| DS26-0197 | 163.9 / 117.2 | 74.8 / 75.0 | 69.6 / 69.6 |
| DS26-0223 | 177.1 / 160.1 | 87.5 / 87.5 | 81.4 / 81.4 |
| DS29-0316 | 166.3 / 165.4 | 120.8 / 120.6 | 107.0 / 107.0 |
| DS26-0036 | 131.5 / 105.5 | 83.3 / 83.4 | 74.8 / 74.7 |

The archived v5 frequencies were evaluated on the common keys from its existing full fit. A lower conditional RMS under the refit can coincide with a worse position, as DS29-0316 shows. On DS26-0197, the additional 71 v5-conditioned observations belonged to two RX2 components on channels 2 and 3. Their residuals after the expanded lean refit were 9.24/9.20 kHz RMS. The archived v5 residuals on those same points were 19.85/19.85 Hz. The expanded lean and compact clock fits both reached about 18.7 km error there. The 495 added DS26-0223 points likewise moved the lean fit to 9.55 km error, with 615.7/617.0 Hz on the added points against 66.5/66.5 Hz in v5. Adding all published conditional support thus exposes a model or weighting mismatch. [Added-support audit](added-support-rf.json) · [Common-point CFO](owner-oracle-frequency.png) · [PDF](owner-oracle-frequency.pdf)

The compact model uses the archived v5 receiver/band offset, shared receiver drift, small band-drift contrast, smooth 30 s clock basis and component offsets. It binds archived pre-RF phase widths and means by NORAD. The effective median widths were 3.91 s on DS26-0197, 2.92 s on DS26-0223, 0.57 s on DS29-0316 and 1.87 s on DS26-0036, versus the lean constant 2.5 s. Those widths share the archive's pre-RF scale estimates, with a Gaussian approximation. Switching the compact full-support fit from the lean covariance to 150 Hz diagonal noise reduced the DS29-0316 error from 5.010/5.078 to 3.089/3.147 km and reduced its RMS to 107.3 Hz. The archived original also includes age-dependent heavy-tailed precision, physical orbital modes, family/point weights, predictive evidence and its own nonlinear optimization. This replay cannot apportion changes among those remaining differences or isolate the compact clock and prior terms individually. [Numerical protocol](PROTOCOL.md) · [Per-point fits](residuals.jsonl.gz)

## Authenticity and reproduction

All four fully authenticated v5 receipts matched their original detector, request, owner-map and archive digests. Each frozen lean catalogue was present in the v5 causal history, which contained 38–49 snapshots. All extracted conditional owners were representable in the lean causal bank. The fit namespace received no reference coordinates. The supervisor opened truth only after sealing fit outcomes. The earlier pass used the raw displayed measurement as if it contained the physical branch. That pass never entered the results here. The corrected run recovers the single component lift from the archived unwrapped track, receiver-corrected peak, conditional residual and calibrated orbit curve. [Source lock](source-lock.json) · [Blind lock](blind-lock.json) · [Input lock](input-lock.json) · [Prediction lock](prediction-lock.json) · [Figure lock](figure-lock.json)

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
scratch="$(mktemp -d)"
taskset -c 4,5 .venv/bin/python -m tools.pipeline_eval.qualification.owner_factor blind "$scratch/panel" --cache "$scratch/cache"
taskset -c 4,5 .venv/bin/python -m tools.pipeline_eval.qualification.owner_factor privileged "$scratch/panel"
taskset -c 4 .venv/bin/python -m tools.pipeline_eval.qualification.owner_factor score "$scratch/panel" --out "$scratch/report"
.venv/bin/python -m tools.pipeline_eval.qualification.owner_factor_figures --evidence "$scratch/report"
.venv/bin/python -m tools.pipeline_eval.qualification.owner_factor_roof --evidence "$scratch/report"
```
