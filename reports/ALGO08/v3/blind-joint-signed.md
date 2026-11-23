# Signed endpoint estimation on the blind joint membership

The direct signed finish recovered the **exact v3 northern position, 302 owners, RF RMS, optimizer path and numerical grid** in both calibration arms. It required **0.202 CPU seconds** for signed qualification and fitting. The restored west-bound endpoint triggered **2.029 CPU seconds** of exterior qualification, bringing the saved solve to **6.659 CPU seconds versus 5.645** for fresh v3. The same exact endpoint policy reproduced both southern v3 positions and kept the previously frozen ownership. [Frozen protocol](blind-joint-signed-protocol.md) · [Numeric summary](measurements/blind-joint-signed-summary.json) · [Full receipts](measurements/blind-joint-signed.json.gz)

## Why the northern fit moved

The north-containing accepted blind and stock models had exactly the same 285 curved observations and 17 predictive observations, roles, signed aliases, satellite labels, family weights and pre-RF history distribution. Both terminal stock arms used the qualified standardized signed phase feature. The ordinary phase means were zero. The adopted means lay between −2.212 and −0.148 s and matched the stock reconstruction exactly. The selected numerical state came from the accepted blind support and the causal archive. The stock endpoint and phase references entered the attribution separately, after the candidate's measured decision. [Original stock-finish attribution](../single-core-2x/solver-stock-finish.md) · [Current attribution receipts](measurements/blind-joint-signed.json.gz)

| North containing | `c = 0` east / north km | Fitted `c` east / north km | Role in the trial |
| --- | ---: | ---: | --- |
| Warm ordinary joint fit | −12.260679 / 0.100082 | −12.178316 / −0.029388 | Existing blind candidate |
| Zero-start ordinary refit | −12.259249 / 0.104569 | −12.189809 / −0.031876 | Off-clock matched-support diagnostic |
| Zero-start signed refit | −12.500000 / 0.034477 | −12.500000 / −0.099028 | Returned candidate |
| Fresh v3 | −12.500000 / 0.034477 | −12.500000 / −0.099028 | Matched stock terminal |

Changing the start alone moved the two endpoints by about 5 and 12 m, leaving both inside the box. With the same zero start and fixed support, the signed means moved both fits to the western face and reproduced every signed optimizer round endpoint and final phase reference. One meter inward at the stock bound decreased the fixed-reference squared objective by 0.000497 / 0.000720 on the ordinary cold models. The signed models increased that same within-model change by 0.001487 / 0.001343. In this case, the independently qualified prior changed the preferred boundary direction. Agreement in ownership and RF fit alone could not establish endpoint parity. [Objective readout](blind_joint_signed.py)

The direct adapter checks the same capture cutoff, pre-RF forecast and chronological and satellite-disjoint qualification as the installed prior. It adjusts phase means only for the current family layout, then runs the original cold event refit on the matching masks and predictive covariance. The original pair passes in both arms before the exterior and publication checks. If history is unqualified or its pair rejects, the adapter keeps the preceding accepted ordinary fit and charges all attempted work. The omitted offers still require the installed exterior check. [Source](blind_joint_signed.py) · [Driver](blind_joint_trial.py)

## Five saved offers

| Offer | Terminal error km `c = 0` / fitted, v3 → signed candidate | Curved RF RMS Hz `c = 0` / fitted, v3 → candidate | Terminal decision |
| --- | ---: | ---: | --- |
| DS30-0008 | 1.639 / 1.512 → 1.086 / 1.080 | 129.703 / 129.663 → 128.821 / 128.753 | Both returned |
| North containing | 0.106 / 0.141 → 0.106 / 0.141 | 5.406 / 5.167 → 5.406 / 5.167 | Both returned |
| North far omitted | — | — | Both withheld |
| South containing | 0.817 / 1.101 → 0.817 / 1.101 | 6.502 / 6.392 → 6.502 / 6.392 | Both returned |
| South far omitted | — | — | Both withheld |

The same qualification adopted the signed pair on every offer. The northern and southern containing positions, path and grid digests match v3 exactly. Their grid each evaluated 137 points. The unsigned southern improvement of 0.520 / 0.494 km disappears under the signed policy. Both far omitted pairs kept their installed exterior withholding. Their provisional in-region fits remained over 52 km from the evaluation references and are reported separately in the numeric receipt. All five finished without full v3 fallback. [Unsigned north](blind-joint-north.md) · [Unsigned south](blind-joint-repair.md)

The dense repair kept the same 4,440 owners and both original roles as its unsigned counterpart. All 4,358 jointly owned observations stayed with the same satellite as v3, with 114 stock-only and 82 candidate-only owners. Both arms passed and built the complete 179-point grid. Within that common candidate support, fitting `c` lowered RF RMS by 0.068 Hz and horizontal error by 0.007 km. Against the unsigned dense repair, signed error changed −0.026 / +0.009 km. Compared with v3 it remained better by 0.553 / 0.432 km through the checked terminal. Geographic scoring used the archived references after inference. [Dense ownership and paired scores](measurements/blind-joint-signed-summary.json) · [Physical reference](../../2026_11_21_ds30_full/reference-audit.json) · [Simulated references](../regional-release/scoring-key.json)

## Charged work

| Offer | Signed update CPU s, including refit | Exterior CPU s | Numerical evidence CPU s | Candidate CPU / elapsed s | Fresh v3 CPU / elapsed s |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0008 | 2.266 | negligible | 6.489 | 38.062 / 38.065 | 54.515 / 54.522 |
| North containing | 0.202 | 2.029 | 0.739 | 6.659 / 6.660 | 5.645 / 5.646 |
| North far omitted | 0.286 | 2.918 | — | 7.426 / 7.427 | 9.398 / 9.398 |
| South containing | 0.187 | negligible | 0.444 | 3.849 / 3.849 | 4.523 / 4.523 |
| South far omitted | 0.161 | 2.727 | — | 6.429 / 6.430 | 6.387 / 6.388 |

North's refit itself took 0.101 CPU seconds and retained the original five rounds per arm. Even a free signed update would leave 6.457 CPU seconds, about 0.812 above fresh v3, because exact stock positions require the exterior evaluation here. The candidate's ordinary path gets an exterior score only at a bound, and this signed update restores that trigger. The off-clock northern attribution took 0.179 CPU seconds and was excluded from the control clock. The current exact replay agrees with the earlier measured stock-finish mechanism. Its small branch times leave no evidence that direct signed creation alone removes meaningful extra refit work.

Dense qualification and prior adjustment together took 0.085 CPU seconds, followed by the 2.181-second original paired refit. The largest remaining stages were cold discovery at 13.774 s, selected grid/evidence at 6.489 s, and single-pass salvage at 5.042 s. The total beat fresh stock by 30.2% on saved inputs and still missed the 24-second budget by 14.062. Eliminating the whole signed stage would leave 35.796 seconds. The lower CPU relative to the earlier unsigned run comes from separate runs. Within this pair the signed stage is measured added work. The paired study contains only these saved controls and measures numerical publication evidence through solve or withholding. [Stage clocks](measurements/blind-joint-signed-summary.json)

## Reproduce

Use the same pinned installed-v3 runner and low-priority core wrapper as the blind joint trial. Add `--repair --signed-finish` to the five fresh invocations for `north-containing`, `north-far`, `south-containing`, `south-far` and `DS30-0008`. Pass the same five names as repeated `--case` arguments to the scorer. The attribution is diagnostic code engaged only on the saved northern containing case. It cannot alter inference or the selected evidence. Ten targeted tests passed. [Wrapper and environment](blind-joint.md#reproduction) · [Owned tests](../../../tests/pipeline_eval/test_algo08v3_blind_joint_signed.py)
