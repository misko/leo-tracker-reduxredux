# Archived covariance detections through the repaired v3 solver

The covariance receiver supplied both dense fixes and the correct containing and far-omitted decisions on the southern simulation. All three cases used the original repaired joint solver and finished without fallback. The dense alternate saved solve used **41.59 CPU seconds**, compared with **45.37** for the same solver on the v3 receiver packet and **59.09** for the checked installed v3 solver. Its complete archived acquisition took **56.20 elapsed seconds** through the sealed detection file. Combining that acquisition, the measured solve and the historical publication allowance gives **101.14 seconds**, or **1.12×** against v3's historical 113.02 seconds. The 2× target is 56.51 seconds. [Protocol](receiver-crossover-protocol.md) · [Scored receipt](measurements/receiver-crossover-summary.json) · [Complete saved solver receipts](measurements/receiver-crossover.json.gz)

## Matched packets and scores

The covariance binary `d44c6032` and the installed v3 binary `2258f592` each processed DS30-0008 and two independent simulated waveforms. Pair receipts and terminals authenticate the native documents. Each comparison shares raw authority, session, causal archive, sample clock, delivery clocks, RF, ordered admitted opportunities and the original exclusion ledger. The dense capture has 6,765 admitted stereo visits and seven excluded. Each simulation has 1,200 admitted stereo visits. Covariance and v3 kept all 7,016 dense selected factors, including 432 at residual rank. Three signed CFOs and three fractional epochs changed. Both simulations matched the 456 selected times, ranks and signed CFOs on each waveform, with numerical score differences. The north packet was bound for transfer and left at the acquisition boundary to limit this trial. [Frozen packet and clock bindings](measurements/receiver-crossover-bindings.json)

The alternate solver received its unmodified native packet, the operator's offer and the causal TLE archive. Both numerical arms shared the retained evidence and original search settings. The scorer loaded the geographic references after all three alternate solver receipts were saved. On the dense case both repaired routes accepted one common support refit. Covariance dropped five of 151 tracks, covering 111 of 3,641 curved and 41 of 949 predictive observations. It kept 3,530 curved and 908 predictive owners in each arm, versus 3,532 and 908 with the v3 detector. Both complete dense grids evaluated 179 points with zero objective replay error. [Repair and stock-detector control](blind-joint-repair.md) · [Geographic references](../../2026_11_21_ds30_full/reference-audit.json) · [Simulated references](../regional-release/scoring-key.json)

Each pair below is fixed-zero and fitted `c`, respectively.

| Saved offer | Installed v3 error, km | Repaired with v3 detector error, km | Repaired with covariance detector error, km | RF RMS, Hz, installed → repaired v3 detector → repaired covariance |
|---|---:|---:|---:|---|
| DS30-0008 | 1.639 / 1.512 | 1.112 / 1.070 | 1.135 / 1.093 | 129.703 / 129.663 → 128.836 / 128.761 → 128.886 / 128.811 |
| South containing | 0.817 / 1.101 | 0.296 / 0.607 | 0.296 / 0.607 | 6.502 / 6.392 → 6.470 / 6.373 → 6.470 / 6.373 |
| South far omitted | Withheld | Withheld | Withheld | — |

The dense covariance error increases relative to the repaired v3 detector were 23 m in each arm. Fitting `c` lowered dense covariance error by 42 m and RMS by 0.075 Hz. It lowered southern containing RMS by 0.096 Hz and increased error by 311 m. The southern containing covariance packet kept the same 266 owners per arm as the repaired v3 detector. The far omission reached the original exterior check and withheld with `both_receivers_support_far_exterior`. The public offers probe a single simulated site and use an existing operator latitude. Near-omission and fresh-site qualification remain open. [Decisions and calibration ablation](measurements/receiver-crossover-summary.json)

## Charged cost and historical screening

| Saved offer | Installed v3 solver CPU / elapsed s | Repaired with v3 receiver CPU / elapsed s | Repaired with covariance receiver CPU / elapsed s | Alternate fallback |
|---|---:|---:|---:|---|
| DS30-0008 | 59.09 / 59.10 | 45.37 / 45.54 | 41.59 / 41.60 | None |
| South containing | 5.25 / 5.25 | 4.05 / 4.05 | 3.74 / 3.74 | None |
| South far omitted | 6.54 / 6.54 | 6.91 / 6.92 | 7.67 / 7.67 | None |

These are single-core saved solves including preparation, fit, evidence and veto. The installed and repaired v3-detector measurements are the previously checked controls. The covariance runs used fresh processes with the identical solver code. Single repeats leave timing variability, including the apparent 3.77 CPU second difference between dense repaired runs. Applying the observed solver time would require acquisition in **11.57 s** for the 2× elapsed target. The covariance run with zero charged filesystem input blocks measured 56.20 s to the detection file, 45.36 further seconds to its original terminal and 104.33 s from launch to complete publication with its original solver. The elapsed stage estimate uses the archived file timestamps. Even with free solving and the 3.34 s historical v3 publication allowance, covariance acquisition exceeds the complete elapsed target by 3.03 s. [Complete covariance pair inventory](../single-core-2x/measurements/covariance-ds30-two-pairs.json) · [Historical v3 stage clocks](first-55/stage-clocks.csv)

The archived covariance run consumed 103.17 CPU seconds on one core. It had 48.14 elapsed seconds remaining after the detection file, yielding **55.04 CPU seconds** as a lower bound on complete acquisition, inclusive of the original receiver verification. Combined with the alternate saved solver the lower bound is **96.63 CPU seconds** before publication, against **55.54** for half of historical v3 CPU. The separate cold v3 run measured 58.96 CPU seconds and 99.53 elapsed seconds to solver entry, with 37.34 CPU seconds in the stereo callbacks. That colder run has a different acquisition stopping point and cache condition. The warm projection uses the detection-file stages and adds publication from the historical warm v3 run. [Cold acquisition instrumentation](acquisition-split.md)

Among archives with a complete dense packet and both simulated counterparts, covariance provided the strongest complete-time alternate. Full-phase measured 62.66 s through the dense detection file and supplied only a 128-visit same-binary simulated acquisition receipt. The terminal variant also supplied dense and northern packets, with 109.21 s complete dense CPU. The wrapped variant's complete physical packet was DS30-0374, a different recording. The covariance algorithm here uses paired covariance accumulation and full floating-point verification. The earlier primary covariance gate saved 5.6–16.7% native CPU on short DS26/DS30 prefixes and lost a verified factor. Those prefix clocks measure a different detector variant and exclude complete authenticated acquisition. [Full-phase stage](../single-core-2x/full-phase-ds30-stage.md) · [Covariance publication](../single-core-2x/covariance-publication.md) · [Prefix gate result](../single-core-2x/receiver-covariance-confirmation.md)

The older DS26/DS29 archives contain signed candidate rows and acquisition variants from different recordings and compact-v5 solver interfaces. The fastest ordinary complete acquisition receipts in the 20-control timing table used 125.18 CPU seconds for four GLRT centers and 152.15 for five. The later optimized ordinary native detector alone used 127.77 CPU seconds on DS26-0036 and 95.64 on DS29-0082 with two pinned cores. Staggered search reached native stereo medians of 18.46–20.42 ms, with 28.16–29.98 ms process CPU per callback and 229.57–251.55 s complete raw handoff. The improved staggered positions came from its older DS26-0144 and DS29-0491 recordings. The reported GLRT speedup ratios apply to those older interfaces and comparators. [Legacy complete timing](../../2026_11_19_receiver_screening/latency-and-support/complete-timing/README.md) · [Optimized ordinary path](../../2026_11_19_receiver_screening/end-to-end/README.md) · [Staggered receiver](../../2026_11_19_receiver_screening/receiver-choice/staggered-whole/README.md)

## Reproduce from sealed detections

Use the shared lock and Python environment in the [repaired joint solver reproduction](blind-joint-repair.md#reproduce). Keep its release and payload setup. Pass the tracked bindings and an empty scratch directory. The alternate invocation measures no raw replay. Twelve targeted component tests passed. [Replay](receiver_crossover.py) · [Scorer](receiver_crossover_score.py) · [Tests](../../../tests/pipeline_eval/test_algo08v3_receiver_crossover.py)

```sh
for joint_case in south-containing south-far DS30-0008; do
  joint_lock env PYTHONPATH="$joint_code:$joint_payload:$joint_release/src:$joint_release" \
    "$joint_release/venv/bin/python" -BPs "$joint_code/receiver_crossover.py" replay \
    "$joint_case" "$joint_code/measurements/receiver-crossover-bindings.json" \
    "$joint_results/$joint_case.json"
done
joint_lock env PYTHONPATH="$joint_code:$PWD:$PWD/src" python "$joint_code/receiver_crossover_score.py" \
  "$joint_results" "$joint_code/measurements/receiver-crossover-bindings.json" \
  "$joint_results/summary.json" "$joint_results/complete.json.gz"
```
