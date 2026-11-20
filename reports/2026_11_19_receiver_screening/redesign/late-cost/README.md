# Fresh same-core cost of late RF preflight

The frozen RF rule and the original aligned compact v5 control each start from complete stored capture-era native GLRT factors and the same causal request. Each pair uses one pinned core, a fresh process per method, single-threaded numerical libraries, and low scheduler priority. The observed worker interval includes native decode, Graph and orbital preparation, the cavity fit, and all late stages through both calibration arms. The launcher interval also includes kernel compilation, process start and the numerical request check. [Protocol](PROTOCOL.md), [locked schedule and sources](plan.json).

The two bypass cases were selected by fixed hash from the 15 previously unmeasured archived bypasses. DS26-0066 checks the branch with a genuine retained identity repair. CPU19 runs the two bypass pairs in opposite orders, and CPU11 runs the retained repair with the guard first. Each pair rebuilt the live numerical likelihood from its complete request. The older archive replay supplied roster eligibility and remains a separate study. [Archive-stage preflight report](../../recovery/late-preflight/README.md).

## Measured bypass on DS26-0261

On the fresh CPU19 matched pair, the guard reduced complete worker wall time from **171.66 to 134.92 s** and process CPU from **156.63 to 117.56 s**. Both positions, likelihood objectives, associated counts and conditional frequency RMS matched exactly. Horizontal error stayed at 1.398 km for `c=0` and 1.374 km with fitted `c`. Conditional RMS stayed at 68.48 Hz and 68.43 Hz. [Both-arm position charts](charts/index.html), [per-arm scores](scores.csv).

| Measured boundary on CPU19 | Aligned wall / CPU, s | Guarded wall / CPU, s |
| --- | ---: | ---: |
| Complete worker | 171.66 / 156.63 | 134.92 / 117.56 |
| Complete launcher | 176.34 / 160.90 | 139.07 / 121.79 |
| Ranking, admission, final, and RF preflight | 49.15 / 41.56 | 0.011 / 0.011 |

The guard took about 2.8 ms wall and 1.6 ms CPU. It avoided all 42 arm-specific omissions and both nominations. The earlier residual search still evaluated 99 nomination grids in each run. The measured late-stage saving was 49.14 s wall and 41.55 s CPU, while the whole worker saved 36.74 s wall and 39.07 s CPU. The stage and complete measurements describe different boundaries. [Measured timing chart](timing.png), [paired stage counters](pairs.json).

## Run coverage and time limits

One of three prescribed pairs completed under the shared 520 s run cap. On CPU11, the retained DS26-0066 guarded and aligned workers timed out after 280 and 233 s. On CPU19, the DS26-0162 guarded worker timed out after 196 s and the aligned worker reached the batch deadline before starting. CPU7 was released late in the study and received the same DS26-0162 schedule under a locked affinity amendment. Its guarded worker completed in 164.77 s launcher wall and 114.06 s launcher CPU. It bypassed the late branches and completed both positions. The aligned worker reached the shared deadline before starting. The paired savings above therefore describe DS26-0261. The retained-repair timing and second bypass have no complete contemporary control. All complete, timed-out and unstarted attempts are in the ledger. [Attempt ledger](attempts.jsonl.gz), [affinity amendment](affinity-amendment.json), [amended worker results](amended-pair.json).

## Reproduction

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python -m tools.pipeline_eval.qualification.late_cost_trial /tmp/leo-late-cost-replay --seconds 520
python -m tools.pipeline_eval.qualification.late_cost_results /tmp/leo-late-cost-replay
python -m tools.pipeline_eval figures --panel screening --variant late-cost-roof --arm both --out /tmp/leo-late-cost-charts
```
