# Reuse the accepted compact position evaluation

The compact secant fit has already computed the full geometry, linearized radio likelihood and bounded posterior at the accepted endpoint when it stops. The default reporting path computes that same result again to derive terminal RF RMS, hardware and phase state, and physical support gates. The optional phase-release build passes the accepted result to those read-only consumers. The optimizer still evaluates the initial point, each finite-difference point, and all original trial proposals with the original operation order.

A callback records the result at the initial and each accepted position. The optimizer can make a later rejected evaluation without overwriting the accepted payload. One endpoint is retained for the current problem, using exact float64 coordinates and the same mask, phase reference, phase widths, aliases, arm and calculation function. A mismatch follows the original calculation. A new fit releases the previous payload. The original signed and cavity paths already use their own cache and continue to do so. This reuse covers the complete model evaluation. Earlier native-bound memoization targeted the lower-level normal solve. [Optimization and witness source](../../../../tools/pipeline_eval/variants/compact_endpoint.py) · [Earlier native memo study](../../streamlined/phase-cache/README.md)

The predeclared panel uses four complete original capture-era native GLRT inputs. Every case uses one pinned CPU, one numerical thread, the same causal TLE and supplied tile, both calibration arms, and a 512 MiB cgroup with zero swap and 180 s limit. Within-core order reverses between cases. Both builds hash every fitted model's track members, family identities, aliases, support mask and phase widths, as well as the complete accepted trajectory and optimizer counters. Conditional RF fit is reported separately from geographic error. The four frozen v5 policy references are included in the position book. [Protocol](PROTOCOL.md) · [Input and build seal](source-lock.json)

## Measurements

All four pairs returned both arms with byte-identical scientific results and identical optimizer-ledger hashes. The candidate avoided 998 wholly repeated reporting calculations, while preserving all 360 fits, 2,555 optimizer evaluations and 24,779 compact C projections. The existing geometry and event caches still run on their original paths. [Trajectory and result parity](parity.json)

| Original recording | Redundant calculations removed | Complete CPU, stock → reuse (s) | Complete elapsed (s) | Peak cgroup charge (MiB) |
| --- | ---: | ---: | ---: | ---: |
| DS26-0026 control | 275 | 74.01 → 63.46 | 82.40 → 66.34 | 283.9 → 303.3 |
| DS29-0174 control | 241 | 70.67 → 71.23 | 76.17 → 73.99 | 345.9 → 348.7 |
| DS26-0138 held | 241 | 75.13 → 70.99 | 76.37 → 80.43 | 323.2 → 374.3 |
| DS29-0357 held | 241 | 106.76 → 108.35 | 110.99 → 117.19 | 382.4 → 367.7 |

Summed complete CPU fell 3.8% and wall fell 2.3%. CPU improved on two cases and wall improved on two. Peak cgroup charge increased on three cases, by up to 51.1 MiB. All capped services completed. Both arms of every case were inside 1.63 km, with conditional RF RMS from 64.82 to 95.52 Hz, and each error and RF value was the same as its direct compact control. [Stage chart](solver-reuse.pdf) · [Measured resources](resources.csv) · [Both-arm scores](scores.csv)

The installed overlay increases the source inventory from 78 to 79. It adds one 126-line Python file and narrowly changes ten existing source files. Both compiled libraries are byte-identical to stock and the same dependencies are required. [Installed diff](installed-delta.patch) · [Source inventory](complexity.json)

## Reproduce

Install the overlay in a new directory and invoke its standard compact position entry with your retained GLRT, track configuration, causal archive and region.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.solver_reuse_build /tmp/compact-endpoint
.venv/bin/python -IB /tmp/compact-endpoint --help
```

The normal stock installer stays available. Rescore the packaged evidence without running the numerical service again.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.solver_reuse_results
```

[Measured resources](resources.csv) · [Both-arm positions and RF](scores.csv) · [Exact support and trajectory audit](parity.json) · [Standard charts](charts/index.html) · [Installed diff](installed-delta.patch)
