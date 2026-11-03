# Fixed-frequency-width continuation

This is an optimization-path experiment, not a fitted noise model. Every selected endpoint is ranked and evaluated under the unchanged original 125 Hz likelihood. Temporary widths of 1000, 500 and 250 Hz let the optimizer traverse a broader likelihood before returning to 125 Hz. Candidates, physical calibration functions, learned-c versus c=0 arms, timing/q/clock priors, bounds and training observations remain unchanged.

## Frozen two-source pilot

Each unit starts from its original fixed-bank fitted-c profile endpoint; the c=0 seed changes only c. Its own RF arm's raw fixed-profile endpoint remains eligible. A fresh 125 Hz continuation and the annealing path each have 1000 actual objective calls and 120 seconds. One incumbent score is charged inside this budget. Annealing stage quotas are 149/150/150/550, plus that incumbent score. Broadened stage objectives are diagnostic only. Selection uses the minimum feasible original-125 training objective; strict stationarity at .001 is reported independently and is never relaxed.

`model.py`, `test_model.py` and `run.py` are pinned in the two launch receipts. Three component tests pass, including bit-exact 125 Hz nesting, nonzero-width gradient finite differences, held-value invariance and exact total-call accounting. Both case seals precede all position and diagnostic-window evaluation. No station location or diagnostic-window/candidate labels are inference inputs.

| Source / RF arm | 125 continuation J | Annealing J | All-point associated, control → anneal | Diagnostic-window associated, control → anneal | Raw anneal KKT / strict |
|---|---:|---:|---:|---:|---|
| S01 fitted-c | 57682.155614 | 57682.155614 | 2517 → 2517 / 4797 | 90 → 90 / 148 | .0040554 / no |
| S01 c=0 | 57691.221825 | 57691.221825 | 2514 → 2514 / 4797 | 40 → 40 / 148 | .0406267 / no |
| S04 fitted-c | 40246.696960 | 39603.694251 | 2803 → 2925 / 3719 | 56 → 72 / 155 | .00114096 / no |
| S04 c=0 | 41637.315845 | 41276.369656 | 2630 → 2687 / 3719 | 61 → 64 / 155 | .00005126 / yes |

S04 fitted-c gains 280 associations and loses 158 against the fixed-profile control. Intersection RMS falls 144.40→140.25 Hz; overall associated RMS falls 147.44→144.88 Hz. Its configured-reference distance remains poor, 260.09→253.11 km. S04 c=0 annealing versus fresh control improves overall RMS 163.79→159.90 Hz and configured distance 258.81→256.21 km. These are different frequency/support and position outcomes, not a localization success. S01 keeps the raw incumbent and gains nothing.

All eight primary outcomes and the original seals remain immutable. `evaluation.json` and `eval_*.npz` contain their exact all-point/new/lost/intersection/position metrics. Model associations are not verified satellite identities.

## Separate numerical evidence

After the pilot was sealed and evaluated, one uniform rule offered an unchanged-model L-BFGS-B finish to every feasible rejected selected endpoint with unused calls/time. It uses at most min(134,1000−used) objectives and min(78,120−recorded active seconds) seconds. This is a **later wall run with a cumulative active-work budget**, not a continuation inside the original continuous deadline. Independent replay/audit calls are counted separately. Four owned/engine tests pass, including invalid-physical-point exclusion and budget/score safeguards.

S01 fitted-c annealing becomes strict with four extra evaluations (KKT .00073092); its matched control remains rejected after 18. S01 c=0 remains rejected after 134 evaluations per method (KKT .00610946). S04 fitted-c annealing remains rejected after 15 evaluations (KKT .00114096), despite a two-ULP-scale objective decrease. Every attempted finish leaves all hard associations and all best-candidate labels unchanged. Raw scientific outcomes remain the primary table above; strictness repairs are separate evidence in `polish_*.json`, `polish_seal_*.json` and `polish_evaluation.json`. No further numerical retry is inferred.

## Remaining-three replication

The same annealing and 125-continuation policy is predeclared on S02/S03/S05, both RF arms. New source `run_remaining.py` preserves raw outcomes and permits the same single numerical finish **immediately inside each unit's original continuous remaining 1000-call/120-second budget**, only for feasible rejected endpoints. Three additional tests verify identical-state finishing, unused-call/time caps, and no finish after acceptance/deadline. All twelve inference outcomes must seal before evaluation. The slight difference in numerical-finishing timing is explicit; it must not be hidden in an all-five hybrid performance claim.

## Uniform all-five raw result

All remaining twelve outcomes sealed before evaluation. `uniform_evaluation.json`, `uniform_fit_*.json` and `uniform_eval_*.npz` normalize the **raw** endpoint from every source under the same policy, explicitly excluding both the pilot's later finishes and the replication's immediate finishes. All new/lost/intersection metrics in this uniform summary use the same original published fitted-c reference state for both RF arms. This differs from the pilot table's own-arm fixed-profile comparison baseline. The underlying endpoint associations are identical.

| RF arm | All-point associated control → anneal / denominator | Diagnostic associated control → anneal / denominator | Strict control → anneal |
|---|---:|---:|---:|
| Fitted-c | 13784 → 14173 / 20084 | 422 → 455 / 693 | 4/5 → 2/5 |
| c=0 | 12372 → 12535 / 20084 | 313 → 357 / 693 | 3/5 → 4/5 |

The raw fitted-c association gain is 389 overall and 33 in the diagnostic windows, but three annealing endpoints fail strict stationarity. The aggregate is therefore descriptive research evidence, not an accepted automatic-analysis result. Ten component/engine tests pass in 2.03 seconds. The raw algorithm uses 10,622 actual objective evaluations across twenty units; source preparation, exact-nesting qualification and postseal auditing/evaluation are separately disclosed. The remaining-three immediate numerical finishes add 45 calls and leave every hard association and best-candidate label unchanged. Those finishes repair neither S02 fitted-c annealing (.00174027) nor S02 c=0 control (.00121443).

| Source / arm | Original125 training-J gain, control − anneal | All-point gain | Diagnostic gain | Configured-reference km control → anneal | Raw anneal strict |
|---|---:|---:|---:|---:|---|
| S01 fitted-c | 0 | 0 | 0 | 132.472 → 132.472 | no |
| S02 fitted-c | 122.184526 | +79 | +13 | 135.377 → 121.133 | no |
| S03 fitted-c | 0 | 0 | 0 | 3.282 → 3.282 | yes |
| S04 fitted-c | 643.002709 | +122 | +16 | 260.094 → 253.111 | no |
| S05 fitted-c | 1250.596844 | +188 | +4 | 4.709 → 2.754 | yes |
| S01 c=0 | 0 | 0 | 0 | 133.318 → 133.318 | no |
| S02 c=0 | 429.539391 | +54 | +42 | 134.430 → 120.074 | yes |
| S03 c=0 | 0 | 0 | 0 | 3.745 → 3.745 | yes |
| S04 c=0 | 360.946189 | +57 | +3 | 258.815 → 256.207 | yes |
| S05 c=0 | 520.807792 | +52 | −1 | 9.682 → 3.337 | yes |

S05 is an accepted optimization gain: fitted-c associated RMS falls 169.78→162.06 Hz, with configured distance 4.71→2.75 km. It is still far from sub-kilometer localization. S02 and S04 remain large geographic failures despite better frequency fit/support. S03 returns to its previous basin. A better in-sample objective is not a position-accuracy guarantee.

| Diagnostic window | Denominator | Fitted-c control → anneal | c=0 control → anneal |
|---|---:|---:|---:|
| 001 | 86 | 79 → 79 | 38 → 38 |
| 002 | 35 | 11 → 11 | 2 → 2 |
| 003 | 27 | 0 → 0 | 0 → 0 |
| 004 | 44 | 10 → 12 | 12 → 17 |
| 005 | 33 | 31 → 29 | 3 → 27 |
| 006 | 72 | 33 → 46 | 36 → 49 |
| 007 | 54 | 54 → 54 | 41 → 41 |
| 008 | 50 | 48 → 48 | 47 → 47 |
| 009 | 34 | 34 → 34 | 8 → 8 |
| 010 | 46 | 25 → 29 | 33 → 30 |
| 011 | 43 | 15 → 15 | 11 → 8 |
| 012 | 66 | 16 → 28 | 17 → 26 |
| 013 | 28 | 22 → 24 | 24 → 24 |
| 014 | 39 | 11 → 15 | 8 → 13 |
| 015 | 36 | 33 → 31 | 33 → 27 |

The uniform policy retains regressions: fitted-c windows005/015 lose two associations each; c=0 windows010/011/015 lose three/three/six. No per-window best state, reference-chosen seed or identity override is applied. Window003 remains entirely unassociated. The observations/candidates are fixed and every final association uses the original 125 Hz density and unchanged signal-versus-clutter criterion.

`uniform_comparison.png` and `.pdf` show the all-five policy. Open endpoint markers indicate rejection. No numerical finishing is mixed into those curves. There is no promotion or production change, no RF collection, and no modification of the sealed earlier experiments.
