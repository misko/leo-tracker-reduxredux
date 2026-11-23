# Perfect lane skipping saves 16.3% of acquisition on the dense v3 prefix

Even with advance knowledge of every signal, skipping the full detector on as many antenna visits as the continuation permits left **83.7% of the measured acquisition time**. Both matched pairs verified the same 128 signed windows and reproduced all 256 published probe rows, including 84 selected factors. The optimal schedule paid for **138 native calls** across the two antennas. Fifty-four of those calls supplied history for later selections even though they published nothing on their own visits. [Frozen question](continuation-skip-protocol.md) · [Timing, per-lane costs and schedules](measurements/continuation-skip.json)

| Installed ALGO08v3, DS30-0008 prefix | Stock CPU | Oracle CPU | Stock elapsed | Oracle elapsed |
|---|---:|---:|---:|---:|
| Oracle first | 0.927 s | 0.787 s | 0.927 s | 0.787 s |
| Stock first | 0.936 s | 0.772 s | 0.936 s | 0.772 s |

The clock covers verified input through writing and checking the prefix detection document. All four timed arms charged zero storage input blocks. The initial measurement, used to select the minimum-cost schedule, took 0.964 CPU s. Native calls on that measurement totaled 0.686 s. Running only the 84 eventual selections would cost 0.318 s, but some would lose the earlier carrier observations required for confirmation. Paying for the cheapest feasible history raises native cost to **0.521 s**; paying for all 146 nonempty visits would take 0.549 s. Paired replays of the chosen schedule used 77.0% of stock native CPU in aggregate.

Under the measured non-native CPU cost, even **after perfect skipping**, the surviving native calls would need a further **2.60× speedup** to halve total prefix acquisition CPU. This calculation divides their summed actual CPU by the remaining half-time allowance in the two pairs. The oracle costs zero to consult and never guesses wrong. A deployable classifier would have to pay for its own decisions.

## Complete saved factor ledgers

| Recording and receiver | Paid lanes / admitted | Later selections | Native CPU, full → optimal | Acquisition CPU with perfect skips / full |
|---|---:|---:|---:|---:|
| DS30-0016 physical, earlier receiver | 515 / 1,426 | 440 | 4.631 → 2.844 s | 4.806 / 6.592 s (72.9%) |
| Southern simulation, earlier receiver | 528 / 2,400 | 456 | 6.357 → 2.796 s | 5.860 / 9.422 s (62.2%) |

The historical acquisition values add the measured original non-native CPU to the optimized native costs. They are projections with a fixed outside cost. Both schedules reproduced all original selected factors through the released continuation. The historical native binary starts with `950c2b94`; the installed v3 prefix used `2258f592`. The physical dense result measures two verified chunks from one recording. It supplies no full-recording timing or new-site position-error distribution.

## How the ceiling was obtained

The solver for the skip schedule considers every feasible run-or-skip history within each receiver, channel and RF. For each opportunity it evaluates the original continuation and keeps the cheapest path to each distinct twelve-opportunity history that still matches every original output. Empty slots advance that history even on a skip. At most 64 histories were live simultaneously in these data. Replaying the selected path through an independent instance checks every output. Small brute-force tests exercise donor costs, competing carriers and empty-slot eviction. An algorithm which replaces the native call or changes the continuation has a different opportunity. [Optimizer](continuation_skip.py) · [Component tests](../../../tests/pipeline_eval/test_continuation_skip.py)

The actual dense replays used one pinned Gauss core under the common benchmark lock. The precomputed schedule and search CPU stay outside the oracle clocks. To reproduce, run the following in this checkout, supplying a fresh output path.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock sudo -n -u leo \
  ionice -c2 -n7 nice -n15 taskset -c 2 env \
  PYTHONPATH="$PWD/reports/ALGO08/v3:/opt/leo-algo08/algo08v3/payload:$release/src:$release" \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 BLIS_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/continuation_skip_trial.py "$output"
```
