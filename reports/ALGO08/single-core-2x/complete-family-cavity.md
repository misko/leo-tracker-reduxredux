# Complete-family cavity after collapsed signed refinement

The cavity recovered the same complete-family reassignment as deployment on the southern portable-v5 input. It improved both covariance positions and left a regression of 0.808 km at fixed zero and 0.668 km with fitted `c` relative to deployment. On the India control the cavity offered no reassignment, and the two positions, residuals and owner maps matched both controls. [Paired evidence](measurements/complete-family-cavity.json)

The frozen covariance solver stops this selection stage after signed refinement. The opt-in cavity retains the full signed context produced by that solver, calls the deployed nomination and fitting functions, and passes the chosen state to the existing exterior guard and evidence callback. [Prior solver trace](portable-south-solver-attribution.md) · [Experimental binding](../../../tools/pipeline_eval/variants/algo08_collapsed_cavity.py)

The cavity uses the same causal candidate catalogue, signed phase hypotheses, observations, masks, weights, and both calibration arms selected by the collapsed solver. The deployed implementation scores the original complete family and competing satellites on held family points. Its existing candidate and trial budgets, positive-gain screen, both-arm residual gates, and corrected fixed-zero loss determine adoption. A separate saved-input worker activates the variant with the pinned covariance specification. [Released cavity implementation](../../../src/leo/analysis/localization_v3/family_cavity.py) · [Original covariance specification](measurements/covariance-posterior-freeze.json)

## Saved-input comparison

The two containing queries are the original southern portable-v5 factors and India waveform detections from the released geographic replay. The India replay previously matched deployment in both endpoints and ownership. Each new solve reused the native document, TLE history, offer, and track configuration of that comparison. The runner checks the original file and archive digests before inference. The published geographic references are used for scoring. The two runs were serialized on Gauss CPU 2 with one numerical thread and low scheduling priority. [Original geographic comparison](covariance-geographic-transfer.md) · [Trial runner](complete_family_cavity_trial.py)

| Containing case and solver | Horizontal error, fixed-zero / fitted | Conditional Doppler RMS, fixed-zero / fitted | Associated points per arm | Saved solver CPU |
|---|---:|---:|---:|---:|
| Portable south, deployed | 0.351 / 0.583 km | 24.107 / 24.089 Hz | 4,149 | 60.305 s |
| Portable south, frozen covariance | 1.429 / 1.339 km | 24.472 / 24.429 Hz | 4,203 | 29.472 s |
| Portable south, covariance with cavity | 1.159 / 1.251 km | 24.103 / 24.070 Hz | 4,203 | 34.692 s |
| India, deployed | 1.017 / 0.751 km | 15.536 / 15.306 Hz | 517 | 9.785 s |
| India, frozen covariance | 1.017 / 0.751 km | 15.536 / 15.306 Hz | 517 | 4.726 s |
| India, covariance with cavity | 1.017 / 0.751 km | 15.536 / 15.306 Hz | 517 | 5.319 s |

On portable south the cavity screened all 1,666 eligible sky candidates for each of ten retained families. It nominated and accepted `61970 → 62508` for both arms, the same replacement selected by deployment. The candidate entered the cavity at exactly the frozen solver’s endpoints and RMS. Its prior conservative and salvage path retained a different support set from deployment, and the cavity kept the candidate’s 4,203 associated points. Both arms’ final owner digests differ from deployment and frozen covariance. The variant had slightly lower conditional RMS than deployment and larger horizontal errors in both arms. Fitting `c` reduced variant RMS by 0.032 Hz and increased its horizontal error by 0.092 km. [Paired evidence](measurements/complete-family-cavity.json) · [Earlier support divergence](portable-south-solver-attribution.md)

The portable nomination used 4.232 CPU seconds and its single paired fit used 0.775 seconds. The full saved solve added 5.220 CPU seconds relative to frozen covariance and ran 1.74× as fast as deployment on that input. The India nomination examined 12 families and 1,225 candidates in 0.651 CPU seconds and offered no fit. Its owner digests agree across all three builds for both arms. These measurements cover two containing solver inputs. Acquisition, complete publication and omitted offers were outside this comparison. [Paired evidence](measurements/complete-family-cavity.json)

## Reproduction

Use the staged inputs from the geographic replay and a fresh local output directory. The command runs just the two augmented solves and builds the score from the existing comparison arms.

```sh
bench=/tmp/leo-algo08v2-2x-bench
trial=reports/ALGO08/single-core-2x/complete_family_cavity_trial.py
flock "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  env PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -BPs "$trial" run "$bench/portable-v5-geodiverse" \
  "$bench/integration-covariance-posterior" "$bench/complete-family-cavity-new"
```
