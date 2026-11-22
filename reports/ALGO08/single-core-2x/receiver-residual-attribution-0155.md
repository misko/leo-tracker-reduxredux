# Which selection changes caused the DS30-0155 position difference?

Restoring the **18 primary-only selection changes** recovers the DS30-0155 position error in both calibration arms. The fitted error falls by **276.7 m**, compared with **269.3 m** when all 24 changes are restored. Restoring the six residual-involved changes alone increases fitted error by **7.7 m**. The error-scale interaction is below **1 m** in each arm. [Scored four-solve receipt](measurements/DS30-0155-residual-attribution.json)

| Input | Selected factors | Associated points per arm | Fixed-zero error (km) | Fitted error (km) | RF RMS, fixed zero / fitted (Hz) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Unchanged conditional | 4,607 | 3,470 | 1.291011 | 1.426219 | 156.077 / 156.064 |
| Restore primary only | 4,623 | 3,495 | 0.964788 | 1.149526 | 155.422 / 155.386 |
| Restore residual-involved only | 4,611 | 3,474 | 1.299388 | 1.433911 | 156.048 / 156.033 |
| Restore all | 4,627 | 3,498 | 0.972393 | 1.156875 | 155.420 / 155.382 |

Both controls reproduced their paired endpoints, RF RMS values and owner digests exactly. The restored-primary endpoints are within **7.7 m** of deployed in both arms, with their own distinct owner digest. Its fixed-zero error improves by 326.2 m relative to the unchanged conditional result, while the residual-only restoration adds 8.4 m. The signed interaction, calculated as restored-all error minus both one-group errors plus unchanged error, is −0.77 m fixed-zero and −0.34 m fitted. These are changes in horizontal error at this recording's scoring reference.

## Four matched saved-input solves

The published conditional result changes 24 of 12,358 ordered antenna-lane selections. The partition uses only the native scan rank before and after the change. A changed row belongs to the residual-involved group if either of its selected factors has rank one. The primary-only group contains 17 primary-to-empty and one empty-to-primary changes. The residual-involved group contains five residual-to-empty and one empty-to-residual changes. These groups were fixed by the runner in commit `6fbb3526f`. [Published conditional pair](measurements/DS30-0155-conditional.json)

Each hybrid starts with the identical saved candidate detector document. Restore the deployed selection on all rows in exactly one of the two groups. The unchanged control keeps the candidate input, and the restored-all control uses the deployed selections at all changed rows. All other probe fields, row order, acquisition times and capture support remain fixed. The hybrid receipts bind their respective selections in the normal analysis digest. Before the solve, the runner checks the original detector documents against their verified terminal bindings.

The four solves use the same frozen composed solver `65b664d4…`, including its batch TLE parser, shared tables, endpoint and recovery reuse, and preparation-GC scope. A fresh process runs each of the four input variants. One shared Gauss lock covers the batch. The solver receives the assigned archive and original offer. Acquisition and publication are bypassed. There is no I/Q replay or further continuation pass. The runner records the calibrated endpoints, RF RMS, associated points and satellite owner hashes from the two-arm result. It verifies both control endpoints before a separate scoring command opens the pinned station reference. [Runner](residual_attribution_trial.py)

The attribution concerns the selection differences presented to the solver. In the original chronological receiver, dropping residual evidence can change a subsequent primary selection through its donor history. The two rank groups identify the observed solver-input changes and do not identify which scout decisions caused each one. This intervention uses one physical development recording.

The four saved solves used 95.67 CPU seconds in total. The test and scoring runs did not invoke additional solves. Four targeted component tests cover the rank partition, preserved probe metadata, exact endpoint control check and reference gate.

## Raw trace of the first two lost primaries

We replayed visits 0 through 69 of the same sealed physical recording. We chose this prefix because it ends at the second observed loss. All 128 admitted antenna-lane selections matched their respective saved publications in both builds. At visits 68 and 69, the two binaries found identical factors on the current window. The conditional receiver had already skipped the residual scan on one earlier window in each lane. That missing measurement reduced the primary's continuation support from three votes to two. [Raw trace and binary identities](measurements/DS30-0155-primary-donor-prefix.json)

| Current visit | Antenna and channel | Missing donor visit | Age of donor | Primary votes with and without donor | Selection after restoring that donor |
|---|---|---:|---:|---|---|
| 68 | RX0, channel 5 | 20 | 2.124 s | 3 → 2 | Original primary |
| 69 | RX0, channel 6 | 21 | 2.125 s | 3 → 2 | Original primary |

The current windows both received full two-scan processing. Restoring the measured frequencies from just the indicated historical window was sufficient in each case. This experiment identifies the mechanism for two of the 17 lost primary observations. The earlier solver intervention restored the whole primary-only group, so the change in position error cannot be apportioned to these two observations. A separate site-independent rescue prototype measured the cost of searching for missing donors prospectively on a different Gauss recording and a southern simulation. [Cost and transfer comparison](receiver-primary-rescue.md)

To reproduce the raw trace, run the following from the research worktree using the pinned release's Python and assets. The account must have read access to the sealed recording.

~~~bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
trial=reports/ALGO08/single-core-2x
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock sudo -n -u leo \
  ionice -c2 -n7 nice -n15 taskset -c 2 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH="$PWD/src:$PWD:$PWD/$trial" "$release/venv/bin/python" -BPs "$trial/primary_donor_trace.py" \
  /tmp/ds30-v2-stage-65b664/DS30-0155/pair.json "$release/assets" 70
~~~

## Reproduce

Run on the research worktree. The assignable pair path points to its original verified local publication, which holds the saved detections and terminal files. The code checks that the archive's inventory hash equals the assigned capture-time hash and the one recorded in the pair.

~~~bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_python=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
algo08_trial=reports/ALGO08/single-core-2x/residual_attribution_trial.py
algo08_output="$algo08_work/residual-attribution-DS30-0155"
algo08_request=/srv/bulk/leo-dev/ds30-full-20261121/snapshot/inputs/DS30-0155/request.json
algo08_reference=reports/2026_11_21_ds30_full/reference-audit.json

flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src:. \
  timeout 600s "$algo08_python" "$algo08_trial" run \
  /tmp/ds30-v2-stage-65b664/DS30-0155/pair.json \
  "$algo08_work/integration-conditional-residual-reviewed" "$algo08_request" "$algo08_output"
PYTHONPATH=src:. "$algo08_python" "$algo08_trial" score \
  "$algo08_output/completed.json" "$algo08_reference"
~~~
