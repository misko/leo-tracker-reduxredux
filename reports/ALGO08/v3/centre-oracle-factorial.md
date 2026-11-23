# Exact phase and precision oracles for the profiled position solver

Giving the cheap solver **both** the released phase reference and curved-group precision recovered the two-arm accuracy gate on weak DS30-0016. North remained outside the gate in all four conditions. Its best paired errors with both oracles were **1.018 / 1.855 km**, versus **0.106 / 0.141 km** for installed v3. No factorial cell passed across both inputs. The fixed Gaussian position proxy stops here. [Frozen protocol](centre-oracle-factorial-protocol.md) · [Summary](measurements/centre-oracle-factorial-summary.json) · [Full sealed traces](measurements/centre-oracle-factorial.json.gz)

## What the two oracles supplied

The repeated unchanged solve verified every original curved and predictive observation, signed alias, receiver-noise scale, causal phase prior and selected arm readout. The extra extraction reconstructed each selected likelihood and reproduced its archived negative twice ELBO **exactly** in all four provider arms. The released precision updates met their \(10^{-5}\) log-precision stopping criterion in all cases. The causal/nominal cell reproduced the preceding iterative trace exactly. Both candidate calibration arms retained the same rows and search budget in all conditions. [One-step owner capture](centre-oracle-step.md) · [Previous iterative control](centre-oracle-iterative.md) · [Provider and row checks](centre_oracle_factorial.py)

The phase factor gives the selected expansion reference by NORAD. The prior mean stays causal. Absolute-phase subtraction and every Doppler and nuisance column are calculated at the trial location, using the original signed frequencies and exact orbit geometry. The weight factor gives the curved group's dimensionless **family power × final Gamma mean precision**, so each curved observation has precision \(p_g\tau_g/\sigma_i^2\) in Hz\(^{-2}\). Predictive noise remains \(\sqrt{2}\sigma_i\) with its own 300 Hz bias. Their conditional Gaussian covariance follows from the same shared nuisance design and candidate location. The transplant copies no fitted residual, offset, posterior mean, site coordinate, or covariance. It leaves the simplified Gaussian nuisance prior in place. The donor values still come from an expensive full fit on the recording. [Released physical prior and weighting](../../../src/leo/analysis/localization_v3/history_position.py) · [Released predictive covariance](../../../src/leo/analysis/localization_v3/event_position.py)

## Geographic accuracy

All pairs are fixed-zero / fitted \(c\). The original limit is 250 m of additional error in **each** arm.

| Same saved input | Weak DS30-0016 error km | North error km |
|---|---:|---:|
| Installed ALGO08v3 | 1.644 / 1.661 | 0.106 / 0.141 |
| Original short publication supplying the oracle | 1.311 / 1.694 | 0.390 / 0.121 |
| Causal phase, nominal weight | 2.864 / 3.603 | 2.226 / 2.327 |
| Selected phase only | 2.860 / 3.561 | 1.339 / 1.880 |
| Selected group weights only | 1.549 / 1.932 | 1.673 / 2.492 |
| Selected phase and group weights | **1.466 / 1.867** | **1.018 / 1.855** |

On weak, the near-uniform effective precision multipliers of 0.169–0.181 change the balance of curved evidence against the predictive data and nuisance prior. Weights account for most of the geographic gain. Their fitted arm alone misses the allowance by 20 m. Adding the phase reference brings both arms within the limit. On North, the multipliers span 0.014–5.242. Phase alone improves both errors, while weights alone worsen the fitted error. Both together reduce the error in each arm. The remaining added errors versus installed v3 are **0.913 and 1.714 km**. [Post-seal scorer](centre_oracle_factorial_score.py)

All 16 fits converged by the original 20 m threshold with two or three accepted steps, nine or twelve profiled evaluations, and no rejected trials. The common original robust readout, using the donor phase reference and powers only for scoring, improves over the causal/nominal endpoint with both oracles in all four arms. North's curved RF RMS in that common readout is **69.54 / 71.31 Hz** with both oracles versus **70.02 / 70.93 Hz** with neither. Its predictive RMS increases from **114.11 / 125.79 Hz to 224.91 / 207.92 Hz**. These changes are separate from the geographic improvement. The two factors identify limited gains inside the frozen Gaussian proxy, with the rest of the released objective and repeated phase refreshes outside this factorial. [Common objective and per-arm RF tables](measurements/centre-oracle-factorial-summary.json)

## Cost of provision and profiling

| Saved case | Original owner and donor fit CPU s | Additional verified extraction CPU ms, both arms | Best-accuracy cell profiling CPU ms, both arms | Whole factorial CPU ms, including checks |
|---|---:|---:|---:|---:|
| Weak | 3.061 | 3.54 | 13.08 | 58.65 |
| North | 4.193 | 7.02 | 20.27 | 106.57 |

These are one-core saved-detector clocks before evidence grids or images. Exact solution audits and all four profiling cells are recorded separately in the receipt. None of the timing measurements produces a qualifying replacement. Nine focused tests passed. No waveforms or new publications were produced. [Tests](../../../tests/pipeline_eval/test_centre_oracle_factorial.py)

Use the prior saved centre-study environment and same pinned source requests. Run `centre_oracle_factorial_trial.py CASE NEW_OUTPUT` once for each case under the shared Gauss lock, then `centre_oracle_factorial_score.py DIRECTORY NEW_SUMMARY NEW_FULL` after both blind outputs seal. [Capture and matching](centre_oracle_factorial_trial.py)
