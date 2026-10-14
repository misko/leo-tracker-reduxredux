# Native-time band-clock extension and original-incumbent control

Adding the calibration capacity identified by the DS22-001 function audit did not fix the combined-position deficit. All nine initial fits and both subsequently prescribed incumbent fits passed strict joint KKT acceptance. The final combined configured-reference distance is 6.245 km, versus 4.501 km for CH1–4 and 2.739 km for CH5–8. The expanded model is not promoted.

| View | Original matched model (km) | Expanded initial nine fits (km) | Expanded after two incumbent fits (km) |
| --- | ---: | ---: | ---: |
| CH1–8 | 5.582157 | 6.245371 | 6.245371 (reused) |
| CH1–4 | 4.381020 | 5.621121 | 4.501394 |
| CH5–8 | 2.779966 | 2.738515 | 2.738515 (previous result retained) |

These are distances to the configured station coordinate, whose DS22 continuity remains unconfirmed. They are not verified ground-truth accuracy. All views use shared discovery and full-training-derived initial states; this is not independent half discovery. Reference coordinates were joined only after the corresponding experiment sealed.

The prespecified model adds 18 receiver-by-band clock interactions, two band drift terms and one band RF contrast. Original geography and satellite timing remain shared. Full-frame fractions, priors, native timestamps and receiver lifts remain fixed across all/low/high likelihood masks. Effective low/high clock, slope and RF coefficients obey the original physical limits through coupled constraints. Original priors are unchanged at zero extension; band-clock precision is the declared `f*(1-f)*P`, while added drift/RF terms are bounded without new Gaussian penalties. Full coupled KKT, including active physical/nuisance constraint normals, retains the 0.001 threshold. No separable numerical finish or acceptance relaxation is used.

Actual zero-extension qualification passed 72 objective evaluations in 36.22 seconds with no fits. All original seed states remained feasible. Objective, old-coordinate gradients and responsibilities replayed exactly; maximum directional derivative discrepancy was 4.17e-8. Six component/driver tests cover native timestamps, exact original nodes/precision, new-coordinate finite differences, coupled bounds/Jacobians, active-bound KKT and a real bounded synthetic fit.

The initial nine fits use the original three seeds and their original 25 km disks in each view. All were stationary, requiring 314–388 evaluations and 7.40–11.41 seconds including the final audit. However, the initial expanded low-view winner had objective 22051.811868, worse than the exactly nested original low-view feasible incumbent at 21596.224349. That demonstrated a search-basin shortfall despite stationarity, not a worse attainable expanded optimum.

The separately frozen incumbent experiment added exactly two fits: the original matched low and high training winners, each with zero extension and its own unchanged winning disk. All previous nine outcomes stayed eligible. The original all-view endpoint differs from the existing initial state only by at most 5.33e-15 in timing coordinates, with exactly equal nuisance values and disk. Its reuse was explicitly qualified: objective/physical-gradient/nuisance-gradient discrepancies were 7.28e-12/3.59e-10/1.14e-12, within the prespecified 1e-8 bound. Six zero-fit evaluations took 52.75 seconds. No third redundant fit ran.

| New incumbent fit | Expanded objective | KKT | Actual evaluations | Complete elapsed (s) | Training selection |
| --- | ---: | ---: | ---: | ---: | --- |
| Low | 21568.690078 | 2.41e-5 | 299 | 15.896 | Replaces weaker initial low basin |
| High | 17527.086791 | 3.08e-5 | 272 | 10.346 | Previous 17520.734698 remains better |

Final selected NLLs are 39588.950275 (all), 21322.554318 (low), and 17244.566087 (high). Each improves its own original matched NLL of 39721.093124, 21337.218785 and 17266.458897. Better training likelihood does not establish better localization: the all-channel configured distance worsened, and it remains worse than both matched halves. The measured calibration representation gap is real, but resolving that gap alone was insufficient in this experiment.

Each fit admits optimizer evaluations for 20 seconds and reserves the final, independently checked gradient evaluation within its 600-call total. The audit follows the optimizer deadline; complete elapsed times are explicitly reported rather than claiming a hard 20-second invocation limit. Total added scientific cost is nine initial fits plus two incumbent fits. No failed fit was retried, no seed was selected by reference, and no held observations were used.

Sources: `7feeccc56` model/solver/pilot/protocol, `e5663df64` pilot evaluator, `2f044ef0d` incumbent control and `76170764e` its evaluator. Evidence is under `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-native-band-clock-{pilot,comparison,warm,warm-comparison}-v1`. The prior DS21-039 three-column band extension lacked these common-clock interactions; this is a distinct, now-negative DS22 experiment.
