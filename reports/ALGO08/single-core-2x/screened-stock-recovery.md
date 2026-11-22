# Screened nomination with deployed trim and recovery

The screened solver reproduced the deployed fixed-zero and fitted endpoints, conditional Doppler RMS and owner maps on both containing offers. It also matched the southern initial gate, all five proposed trims, retained curved observation identities, signed incumbent and cavity decision. Recovering this agreement took 50.89 solver CPU seconds on the southern input, compared with 34.69 for the cavity-only variant and 60.30 for deployment. [Containing evidence](measurements/screened-stock-recovery-containing.json)

Restoring the complete-family cavity recovered deployment’s winning reassignment on the portable southern input. Its positions still differed because the collapsed earlier fit kept different slices of three fragments. This follow-up routes the existing screened nomination through the deployed conservative recovery, historical family policy, signed prior and complete-family cavity. It uses the already published two-refresh screen for the ranked initial branches, then runs the remaining three updates on the selected branch. Nonfinite scores use the existing full comparison. [Cavity restoration](complete-family-cavity.md) · [First support divergence](portable-south-solver-attribution.md) · [Earlier screened nomination test](solver-stock-finish.md)

The experimental binding retains the deployed trim and paired gates using the scan’s original causal candidate catalogue. It selects the regular deployed inference route before the frozen covariance composition would install collapsed inference. The parent composition still applies causal preparation and discovery reuse, stable recovery reuse, shared cavity projection, posterior grid handoff and the bound-triggered exterior guard. [Binding](../../../tools/pipeline_eval/variants/algo08_screened_stock_recovery.py) · [Frozen composition](measurements/covariance-posterior-freeze.json)

The matched inputs are the published southern portable-v5 detector factors and India waveform detections. Each solve validates the same saved native bytes, causal orbit collection manifest and offer used by the installed and frozen covariance controls. Both fits use the original track configuration and the two calibration arms. The published geographic references enter scoring. [Original comparison](covariance-geographic-transfer.md) · [Trial runner](screened_stock_recovery_trial.py)

## Containing offers

| Saved case | Error with screened stock recovery, fixed-zero / fitted | Conditional Doppler RMS, fixed-zero / fitted | Exact deployed owners per arm | Deployed / frozen covariance / cavity only / screened stock solver CPU |
|---|---:|---:|---:|---:|
| Portable south | 0.351 / 0.583 km | 24.107 / 24.089 Hz | 4,149 | 60.305 / 29.472 / 34.692 / 50.885 s |
| India waveform | 1.017 / 0.751 km | 15.536 / 15.306 Hz | 517 | 9.785 / 4.726 / 5.319 / 5.747 s |

The screen completed nine initial phase updates on each input. It kept the southern third-ranked branch at two updates and continued that branch through five, reaching the same initial endpoint and track gate as the deployed five-update comparison on all three branches. The India screen selected the first branch. An early screen can choose a different branch when its two-update ordering differs from the five-update ordering. [Earlier initial screen protocol](solver-stock-finish-protocol.md)

The southern conservative stage retained the same fragments as deployment. Its three previously different trim lengths were again 123, 164 and 144 points. It proposed the same 19-point fragment that deployment later rejected. The signed incumbent matched in both calibration arms, including observation support, phase means, weights and predictive entries. The same 443 points changed satellites in the accepted complete-family cavity. India ran the deployed conservative stage without trim proposals, and its cavity offered no replacement. The previous India receipt provides endpoint and owner controls. [Southern deployed trace](portable-south-solver-attribution.md) · [Containment stage evidence](measurements/screened-stock-recovery-containing.json)

Compared with the cavity-only variant, screened stock recovery added 16.194 measured solver CPU seconds south and 0.429 in India. Its southern conservative stage took 31.58 elapsed seconds, including the recovery trace readout. Both runs were on Gauss core 2 with one numerical thread and low scheduling priority. The CPU columns compare separate saved-solver invocations. [Cavity-only comparison](measurements/complete-family-cavity.json)

## Omitted offers

After both containing controls matched, the same solver replayed the two original omissions with their published regions and the same detector evidence. [Omission evidence](measurements/screened-stock-recovery-omitted.json)

| Saved case | Deployed | Frozen covariance | Screened stock recovery | Deployed / frozen covariance / screened stock solver CPU |
|---|---|---|---|---:|
| Portable south, 57.026 km outside | False fix · 89.786 / 89.786 km | Withheld both | Withheld both | 84.653 / 55.776 / 89.591 s |
| India, 1.500 km outside | False fix · 1.580 / 1.534 km | False fix · 1.580 / 1.534 km | False fix · 1.580 / 1.534 km | 9.477 / 5.394 / 6.430 s |

Both omission runs reproduced the full frozen regional guard diagnostics. In the southern case both receivers supported the same point 50 km beyond a face, and both arms were withheld with `both_receivers_support_far_exterior`. The screened stock solve used 4.938 more CPU seconds than deployment on this input. The India guard’s two receivers preferred a point 3.125 km beyond the face, below its existing 25 km clearance requirement. It kept both false fixes with the same endpoints, RMS and owner digests as deployment and frozen covariance. [Omission evidence](measurements/screened-stock-recovery-omitted.json)

## Reproduction

Use the staged released geographical inputs and a fresh local output directory. The runner verifies the frozen specification and the historical screen source. It measures saved solver execution through the selected evidence packet.

```sh
bench=/tmp/leo-algo08v2-2x-bench
trial=reports/ALGO08/single-core-2x/screened_stock_recovery_trial.py
flock "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  env PYTHONPATH=src:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -BPs "$trial" run "$bench/portable-v5-geodiverse" \
  "$bench/integration-covariance-posterior" "$bench/screened-stock-containing-new" matched-tile
```

Use `omitted-tile` and a fresh output directory to replay the omission pair.
