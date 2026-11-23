# Saved 8 ms factor crossover on public North and DS30-0016

The 8 ms receiver’s **additional lanes explain most of the northern fixed-calibration regression and the extra numerical solve work**. Adding them to the intact 12 ms packet moved the error from 0.390 to 0.665 km, close to the full 8 ms result of 0.682 km. Two of the 652 added lanes joined prepared tracks and one became a final owner. The graph and subsequent orbital fit changed for other lanes. On DS30-0016 the same addition had no effect on the full 8 ms fix. Measured replacements on shared lanes and the loss of 12 ms-only lanes accounted for that recording’s improvement. A frozen causal margin rule retained the physical benefit and left the northern regression intact. [Frozen protocol](eight-ms-crossover-protocol.md) · [Complete paired receipts](measurements/eight-ms-crossover.json.gz)

## Factor and support comparisons

The three digits in each cell respectively switch to 8 ms measurements on shared signed receiver/start-counter IDs, add factors available only at 8 ms, and drop factors available only at 12 ms. Shared IDs include factors whose wrapped timing or signed CFO changed by more than the prior tolerance. The original 20 ms full anchors stay identical. The six intermediate cells carry private derived identities and require both original packets. Every cell rebuilt the installed graph with its original supplied region, causal archive, native regional options and both calibration arms. The exact saved 12 ms and 8 ms endpoints reproduced the original detector, terminal, owners, numerical grid, path and all figure hashes. Named ALGO08v3 errors were 0.106/0.141 km on North and 1.644/1.661 km on DS30-0016. [Raw aperture controls](eight-ms-physical.md)

| North containing | Error fixed / fitted (km) | RF RMS fixed / fitted (Hz) | Saved solve CPU (s) | Graph rows / curved tracks / final owners |
|---|---:|---:|---:|---:|
| `000` Original 12 ms | 0.390 / 0.121 | 69.40 / 70.86 | 3.621 | 485 / 13 / 347 |
| `100` Replace shared | 0.483 / 0.108 | 8.95 / 8.34 | 3.721 | 491 / 14 / 347 |
| `010` Add 8 ms-only | 0.665 / 0.175 | 117.47 / 118.64 | 3.915 | 501 / 15 / 418 |
| `001` Drop 12 ms-only | 0.390 / 0.121 | 69.40 / 70.86 | 3.685 | 485 / 13 / 347 |
| `110` Replace and add | 0.682 / 0.158 | 96.75 / 97.68 | 3.862 | 504 / 15 / 377 |
| `101` Replace and drop | 0.483 / 0.108 | 8.95 / 8.34 | 3.496 | 491 / 14 / 347 |
| `011` Add and drop | 0.665 / 0.175 | 117.47 / 118.64 | 3.871 | 501 / 15 / 418 |
| `111` Original 8 ms | 0.682 / 0.158 | 96.75 / 97.68 | 3.843 | 504 / 15 / 377 |

Adding the 652 8 ms-only lanes increased fixed error by **199–275 m** in all four comparisons with the other switches held fixed. Added lanes also increased RF RMS in both arms. From the 12 ms input they changed the track grouping of 19 shared graph rows and the curvature status of 28. Final ownership gained 73 and lost two rows. From `101`, adding the same 652 lanes gained 32 final owners and lost two. Swapping common measurements alone reduced fixed RF RMS from 69.40 to 8.95 Hz while raising fixed position error by 93 m. Dropping all 135 12 ms-only lanes changed no North graph, owner set, endpoint or RF RMS in any of the four matched comparisons. Even with oracle exclusion of every added lane, cell `101` missed the fixed 250 m gate against v3 by 127 m. [Per-cell graph and owner counts](measurements/eight-ms-crossover.json.gz)

| DS30-0016 | Error fixed / fitted (km) | RF RMS fixed / fitted (Hz) | Saved solve CPU (s) | Graph rows / curved tracks / final owners |
|---|---:|---:|---:|---:|
| `000` Original 12 ms | 1.311 / 1.694 | 121.53 / 120.29 | 2.634 | 354 / 3 / 116 |
| `100` Replace shared | 0.881 / 1.020 | 142.52 / 141.93 | 2.689 | 352 / 4 / 124 |
| `010` Add 8 ms-only | 1.311 / 1.694 | 121.53 / 120.29 | 2.648 | 353 / 3 / 116 |
| `001` Drop 12 ms-only | 1.195 / 1.481 | 115.36 / 114.89 | 2.674 | 332 / 4 / 115 |
| `110` Replace and add | 0.858 / 0.972 | 142.53 / 142.00 | 2.621 | 353 / 4 / 125 |
| `101` Replace and drop | 0.501 / 0.997 | 134.03 / 133.74 | 2.579 | 315 / 3 / 115 |
| `011` Add and drop | 1.195 / 1.481 | 115.36 / 114.89 | 2.682 | 331 / 4 / 115 |
| `111` Original 8 ms | 0.501 / 0.997 | 134.03 / 133.74 | 2.552 | 301 / 3 / 115 |

Physical addition changed fixed error by 0 to −23 m and fitted error by 0 to −48 m across the four matched comparisons. The 98 added lanes contributed zero owners in the original 8 ms fix. Replacing common factors yielded a **430 m fixed / 674 m fitted** improvement on the original support. Removing the 67 lost lanes after that replacement improved the fixed arm by another **380 m**, yielding the exact final 8 ms positions, RF RMS and owners with all 98 additions absent. The fixed-arm gains came with higher RF residuals than 12 ms. [Coordinates, signed input digests, and separate RF results](measurements/eight-ms-crossover.json.gz)

## Solve cost

The North addition raised solve CPU by **0.141–0.347 s** across the four matched comparisons. The saved original endpoints rose 3.621→3.843 s. Input preparation rose by 0.022 s and later numerical work rose by 0.200 s. The native regional projector evaluated 9.84→10.52 million cells and reused cold catalogue rows increased from 5.40 to 6.21 million cells. Cold ranking and standard numerical evidence rose by 0.068 and 0.075 s respectively. The separate raw experiment measured a 0.358 s numerical increase and a 0.139 s complete CPU increase alongside lower acquisition CPU. Physical saved endpoints fell by 0.082 s and the raw numerical stage fell by 0.299 s. Times are single launches. North cells with identical scientific outputs still differed by up to 0.226 s, so fine timing differences have appreciable variation. Saved clocks exclude waveform acquisition and give no additional raw throughput estimate. [Per-stage and process clocks](measurements/eight-ms-crossover.json.gz) · [Original raw measurements](eight-ms-physical.md)

## Causal margin check

The frozen 0.031623 fractional margin gate scaled the native 0.025 by `sqrt(8/5)` using the nominal origin counts. This approximates how independent per-origin noise would change the standard error of an average. It used only current 8 ms factors and the original full-anchor schedule. Exact/roll correlation, peak selection and confirmation groups can change the actual variance. Prior carrier-history and stereo rules were separate experiments. [Frozen local gate](eight-ms-crossover-protocol.md) · [Earlier stereo/history test](short-stereo-evidence.md)

| Case | 8 ms-only factors kept | Shared factors kept within the prior match tolerance | Both errors after gating (km) | Gate |
|---|---:|---:|---:|---|
| North containing | 533 / 652 | 473 / 474 | 0.682 / 0.158 | Fixed arm fails |
| DS30-0016 | 61 / 98 | 285 / 285 | 0.501 / 0.997 | Passes, including against unfiltered 8 ms |

The margin screen removed 154 North and 42 physical nonanchor factors. Both entire prepared graph partitions and final owner sets, both endpoint pairs, and all four RF RMS values stayed exact. It retained a larger share of North’s disruptive surplus than of the physical surplus. The saved packet construction took 12.2 ms of CPU on North and 5.6 ms on DS30-0016, including hashing. The physical transfer preserved its gains, and North falsified the proposed gate. The availability label requires a second measured aperture, so the useful offline contrast supplies no causal classifier. A prior timing/CFO stereo history approach supplies no independent classifier for this result. [Margin runs and retained strata](measurements/eight-ms-crossover.json.gz)

## Reproduce

Use the existing sealed raw outputs at `/dev/shm/leo-eight-ms-north` and `/dev/shm/leo-eight-ms-DS30-0016-warm`. Run `eight_ms_crossover.py run CASE OUTPUT GEOGRAPHIC_SO` with `CASE` set to `north` or `physical`. For North, add `--regional REGIONAL_SO`. Use `--margin-only` in a fresh output for the corresponding guard. Run `eight_ms_crossover_score.py OUTPUT RECEIPT` and add `--crossover FACTORIAL_OUTPUT` when scoring a margin arm. Use the original recording-readable account, native libraries, one-thread environment, Gauss CPU 2, `gauss.lock`, `nice -n15` and `ionice -c2 -n7`. Put the checkout and `src` first for the scorer. The timed workers bind the installed solver payload. No raw I/Q payloads were opened. All 18 saved processes published two calibration arms, standard position paths, full 137-point or 179-point grids and 144 verified PNGs. Forty-one focused tests passed. [Driver](eight_ms_crossover.py) · [Read-back scorer](eight_ms_crossover_score.py) · [Component tests](../../../tests/pipeline_eval/test_eight_ms_crossover.py)
