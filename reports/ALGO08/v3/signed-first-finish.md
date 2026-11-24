# Signed-first final fit on the proposed main roster

The signed-first schedule skipped the ordinary fit on saved DS30-0316 and cut the combined final-fit charge from **0.736 to 0.491 CPU s**. Both published positions, RF RMS, terminal, all 2,002 ordered owners per arm, adaptive map and eight PNGs matched the current saved control. The new process took **11.367 s through exit versus 10.412 s** for the archived control. The complete-process gate failed, so the frozen dense transfer did not run. [Protocol](signed-first-finish-protocol.md) · [Measurements](measurements/signed-first-finish.json.gz)

## What becomes available before the ordinary fit

After cold discovery, retained-support gates, salvage, confidence-based powers and predictive nomination, `finish_pair` receives a fixed **proposal** comprising the original scan, node, curved mask, predictive entries, weights, causal model and unadjusted phase means. The named final fit uses these fields, applies the qualified signed prior, and starts its released five-refresh optimizer at the region centre and zero phase for both calibration arms. It never reads the ordinary fitted sites, phases or likelihood outputs when the roster is already fixed. [Ordinary route](blind_joint_finish.py) · [Signed qualification](blind_joint_signed.py) · [Released refit](../../../src/leo/analysis/localization_v3/event_position.py)

Ordinary admission decides whether this proposal is sufficient. `pair_passes` requires compatible tracks and in-region finite positions from both arms, and enforces the phase-change limit when predictive checks are included. Failure can trigger a shared endpoint repair or one deletion/refit pass. That pass reads both ordinary failure lists, ordinary endpoints and phase states, and can change the curved mask, predictive support flags, weights and means. On the dense adaptive hybrid the two original ordinary arms failed different curved tracks. Repair removed 91 curved and 35 predictive observations before the released signed fit. A passing early signed pair on that original proposal could retain a different roster. [Pair gates](../../../src/leo/analysis/localization_v3/history_policy.py) · [Ordinary repair](blind_joint_repair.py) · [Endpoint trim](endpoint_track_repair.py)

The prototype preserves the isolated-family provisional branch and its original endpoint repair and only tries the early fit on the ordinary main proposal. It runs at most one early genuine named pair against the exact current proposal and prior. If that attempt passes the signed gate, the named result advances to the original exterior decision and evidence path. This substitutes signed admission for ordinary admission on that branch. If the attempt is unqualified, fails numerically or fails either signed gate, the original ordinary, repair and signed sequence proceeds. That can pay for a separate named pair with the final repaired roster. No early failure occurred in the one measured worker. Five component cases cover the early acceptance, qualification decline, pair rejection, exception, and preservation of provisional priority. [Research implementation](signed_first_finish.py) · [Tests](../../../tests/pipeline_eval/test_signed_first_finish.py)

The lighter estimator used each ordinary endpoint and posterior to initialize a different signed optimization. Here the ordinary states are omitted on acceptance and the released fit is unchanged. The earlier named survivor wrapper already used the same named fit after ordinary acceptance. The constrained rescue work instead avoids a second arm of a rejected alternative after its first completed original gate. The pre-signed named hybrid begins with predictive admission already paid and skips held-family nomination; it cannot remove the earlier ordinary fit. [Lighter estimator](lighter-joint-estimator.md) · [Named survivor finish](named-survivor-fit-0402.md) · [Constrained rescue](paired-veto-0402.md) · [Pre-signed hybrid](pre-signed-hybrid.md)

## Recorded fit costs and their limits

| Saved route | Ordinary CPU s | Additional repair CPU s | Original signed total CPU s | What an early attempt faces |
| --- | ---: | ---: | ---: | --- |
| DS30-0016, combined all-visit 8 ms | 0.020 | 0 | 0.118 | Original main pair passed; small saving ceiling. |
| DS30-0316, current adaptive | 0.235 | 0 | 0.502 | Original main pair passed; the matched publication was eligible. |
| DS30-0008, original combined 8/12 ms hybrid | 0.662 | 0.270 prep + 0.460 refit | 2.404 | Original main pair failed; the later fit used repaired support. |
| DS30-0008, same hybrid with adaptive map | 1.001 | 0.348 prep + 0.513 refit | 2.381 | Same repair; 1.862 s ordinary-plus-repair is a gross policy-change ceiling. |
| DS30-0402, named survivor hard case | 0.676 | 0.355 shared endpoint repair | 2.484 | The preserved provisional branch adopted a shared endpoint trim before the signed fit. |
| DS30-0374, signed-history rejection | 0.465 | 0 | 0.047 | Unqualified history, so no genuine early pair can replace the ordinary. |

The first three timing columns are disjoint within each publication. The 0402 ordinary clock is a copy of its provisional pair clock and is counted once. The combined repair preparation in 0008 includes changing the observation support. An early accepted different roster receives no exactness credit for skipping that repair. A rejected early trial adds a named-pair charge and can erase several successes: for scale, a 0.491 s failed attempt costs about twice the 0.235 s ordinary allowance on medium. The additional signed work on a rejected dense proposal has no measured cost, and the 2.381 s later repaired pair gives its scale only. [Weak saved composition](weak-all8-combined.md) · [Dense combined fit](dense-hybrid-combined.md) · [Adaptive controls](live-adaptive-grid.md) · [Hard active fit](named-survivor-fit-0402.md) · [Hard qualification decline](named-final-0374.md)

## DS30-0316 publication through exit

| Matched saved boundary, CPU seconds unless noted | Archived ordinary-first | Signed-first |
| --- | ---: | ---: |
| Ordinary pair and gates | 0.235 | 0 |
| Signed stage including qualification and witness | 0.502 | 0.491 |
| Both stages | 0.736 | 0.491 |
| Original proposal work excluding the fit charge at that point | 3.211 | 3.652 |
| Standard numerical evidence | 0.850 | 0.911 |
| Eight-figure renderer | 1.008 | 1.068 |
| Process CPU through exit | 10.404 | 11.338 |
| Process elapsed through exit | 10.412 | 11.367 |

The exact named arms took 0.193 and 0.218 CPU s in the new worker. The scope includes the original qualification and adjusted means, a full original fit in each arm, and the likelihood witness. There was no ordinary, repair, inference retry or second named fit. The fit charge fell 0.245 s, while other process work was 1.179 CPU s higher. The new process logged 144 input blocks and nine major faults versus zero for the archived control. These process counters cannot assign the differences in other stages or identify the files responsible. The comparison consists of one fresh candidate and a sealed historical control on the same payload. It establishes the removed fit and its charge, and supplies no through-exit gain or estimate of repeat variance. [Full stage receipt](measurements/signed-first-finish.json.gz)

Both controls kept 2,002 ordered owners and roles per arm with the same terminal endpoints and phase state. Horizontal error was **1.916770 / 1.833652 km**, and terminal RF RMS was **99.594003 / 99.435320 Hz** for fixed-zero and fitted calibration. The separate renderer residual RMS also agreed at 152.596652 / 139.858754 Hz. The original 24-probe regional result, exterior result, exact portable preparation, all 624 compact rank calls, 108 adaptive map positions and all eight figure bytes and decoded pixels agreed. Each PNG read was verified and reused. The path, map and terminal retain the original bindings. The reference was used only after the worker exited. [Adaptive control evidence](measurements/live-adaptive-grid-medium.json)

## Reproduction

Use the signed schedule in `3e7cae126`, its checked original saved inputs and matched adaptive control, and a fresh tmpfs directory. Run `signed_first_trial.py launch DS30-0316 OUT` with the installed release Python and this checkout and its `src` on `PYTHONPATH` under the shared Gauss CPU 2 lock, nice 15, best-effort I/O priority 7 and one numerical thread. Run `compare DS30-0316 OUT` against the sealed local products after exit. The first isolated launch stopped before worker admission because it could not resolve the local schedule import; the corrected explicit path admitted the single measured publication. Post-processing compared grid science without its timing fields and read RF RMS from the authoritative terminal separately from renderer diagnostics. Neither adjustment reran inference. Eighteen focused and adjacent tests passed. [Runner](signed_first_trial.py)
