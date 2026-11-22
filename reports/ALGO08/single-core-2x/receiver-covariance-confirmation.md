# Independent confirmation of the primary covariance gate

**Do not advance the primary gate.** It lost one verified factor on DS30-0016 at the original cutoffs. It still reproduced each selected continuation in both passages and all 41 publication-linked DS30 selections. A continuation vote record and the ordered factors changed. The primary gate saved native CPU on both passages. [Frozen selection plan](receiver-covariance-confirmation-plan.json) · [Ordered factor, vote and timing receipt](measurements/receiver-covariance-confirmation.json.gz)

| Physical passage | Scheduled / admitted visits | Skipped primary lanes / admitted lanes | Exact retained factors / frozen factors | Cold-start selections, both arms | Native CPU saved in two repeats |
|---|---:|---:|---:|---:|---:|
| DS30-0016 visits 64–127 | 64 / 58 | 46 / 116 | 66 / 67 | 4 | 12.4% to 16.7% |
| DS26-0036 visits 1088–1123, weak-carrier passage | 36 / 36 | 17 / 72 | 50 / 50 | 0 | 5.6% to 9.2% |

DS30 lost a primary factor at scheduled visit 116, receiver 1. The frozen scout returned **+424.063 kHz** with exact and rolled scores of 0.092817 and 0.039060, a **0.053757** margin against the 0.025 verifier threshold. Its leading covariance share was 0.078434 and the first two modes held 0.154125. Both fell below the original lower-edge cutoffs, 0.078894 and 0.155840. The factor received two votes when using the prior published history, below the continuation requirement of three. The gate changed the vote record from `[2]` to `[]`. [Failed lane and linked vote records](measurements/receiver-covariance-confirmation.json.gz)

DS26 retained all 18 residual factors. At the earlier contested visit 1111, receiver 0, the frozen detector returned both a −123.023 kHz residual factor and a −88.790 kHz primary factor. The gate kept both exactly. DS26 contributed no selected continuation in its cold-start replay. [Earlier weak-carrier evidence](../../2026_11_20_single_scan_glrt/README.md)

## Inputs and comparisons

The plan was committed at `ba23596d0` before opening confirmation I/Q. It used the sealed DS30 chunk containing the previously documented selection at visit 68 and the first 36 visits of the DS26 chunk containing the known contested visit 1111. Both physical passages were separate from the initial covariance samples by I/Q digest. The earlier public simulations already supplied the available simulated slices. This run evaluated 100 scheduled physical visits from two sealed chunks. The reader verified both touched chunks in full and used the released capture-admission check. Six DS30 windows failed that check. [Plan and capture pins](receiver-covariance-confirmation-plan.json) · [Earlier DS30 selection](receiver-residual-schedule.md)

The two gate/control timings compare the same instrumented build with the primary gate enabled or disabled. An additional genuine `950c2b94` arm reproduced the unrestricted instrumented factors and cold continuation outputs. Comparisons packed the factor fields as binary values and compared their order. All arms saw the same admitted I/Q and started with empty continuation histories. A separate DS30 check seeded each arm's continuation state with the same prior frozen ledger and re-evaluated the measured passage. The genuine `950c2b94` and unrestricted control matched the released 41 selections, and the gated arm returned the same 41 exact factors. The dropped, unselected factor remains a qualification failure. [Original factor ledger method](receiver_factor_ledger.py) · [Confirmation runner](receiver_covariance_confirmation.py)

Native timing includes lane conversion and recentering, FIR decimation, covariance, and the remaining processing on each reached pass. DS30 native CPU changed from 405.45 to 337.84 ms and from 390.26 to 341.92 ms. DS26 changed from 264.87 to 240.55 ms and from 256.80 to 242.47 ms. The comparison used one pinned Gauss core with low CPU and I/O priority, one numerical thread, and the shared benchmark lock. The scope was the receiver and continuation. [Detailed receipt](measurements/receiver-covariance-confirmation.json.gz)

```sh
flock "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 sudo -n -u leo -- \
  env PYTHONPATH="$PWD:$release/src:$release" OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs "$report/receiver_covariance_confirmation.py" \
  "$report/receiver-covariance-confirmation-plan.json" "$report/measurements/receiver-covariance.json.gz" \
  "$bench/receiver-stencil.so" "$bench/receiver-covariance-probe.so" "$release/assets" \
  "$bench/ledger-DS30-0016.json.gz" "$published_detections"
```
