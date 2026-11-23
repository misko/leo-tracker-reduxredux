# Mixed stereo and singleton visits at 40% native call duty

The mixed schedule failed the physical accuracy and overall timing gates in both antenna orientations. On DS30-0016, the complete full-catalogue route returned **1.644 / 1.661 km** of horizontal error for `c = 0` and fitted `c`. The primary schedule returned **3.291 / 3.222 km**, and the inverted schedule returned **2.960 / 2.847 km**. Both southern containing runs passed the 250 m per-arm screen, and both displaced runs completed the original two-receiver exterior check and withheld. The projected complete acquisition and solve CPU was 70.4% to 77.4% of full across the paid runs. [Frozen protocol](mixed-stereo-paid-protocol.md) · [Scored results and stage clocks](measurements/mixed-stereo-paid-summary.json) · [Full fit and schedule receipts](measurements/mixed-stereo-paid.json.gz)

## Paid work and RF coverage

Each complete chronological group of five visits on a fixed channel, RF and edge keeps both antennas at visit 0, one antenna at visit 2 and the opposite antenna at visit 4. The antenna order alternates with both RF-stream ordinal and group ordinal. The inverted mask flips every singleton on the same time axis and preserves all simultaneous stereo visits. Every retained visit belongs to the original verified ledger. Unfinished final groups are unpaid. Each antenna receives exactly two calls per complete group, with no reference position, signal outcome or earlier solver state in the schedule. [Mask construction and peak selection](mixed_stereo_paid.py)

| Saved input | Original antenna calls | Paid antenna calls per orientation | Paid stereo buffers | Buffers measured at both antennas | Paid calls per antenna | Native CPU s, complete / primary / inverted |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0016 | 1,426 | 564 (39.6%) | 423 | 141 | 282 | 4.631 / 1.855 / 1.862 |
| Southern simulation | 2,400 | 960 (40.0%) | 720 | 240 | 480 | 6.357 / 2.515 / 2.515 |

The full recordings contain eight original RF streams each. The physical mask covers 141 groups across the eight streams, leaving eight final visits unpaid. The southern mask covers 30 groups in each stream and has no final remainder. The earlier one-third stereo mask paid 476 and 800 antenna calls for 238 and 400 stereo buffers, respectively. Earlier interlacing paid the same 476 and 800 calls and touched 473 and 800 buffers. In each complete interlaced triple the antennas measured distinct times. The mixed schedule buys more native calls than either prior proposal and revisits fewer distinct buffers than interlacing. [One-third stereo costs](paid-graph.md) · [Interlaced measurements](measurements/interlaced-lanes.json) · [Per-stream schedule and ledger charges](measurements/mixed-stereo-paid-summary.json)

## Paired RF and position outcomes

| Saved offer | Mode | Horizontal error, zero / fitted (km) | RF RMS, zero / fitted (Hz) | Owners per arm | Geometry result |
|---|---|---:|---:|---:|---|
| DS30-0016 containing | Complete | 1.644 / 1.661 | 109.375 / 109.479 | 109 | Returned |
|  | Primary | 3.291 / 3.222 | 119.454 / 118.830 | 56 | Returned, above error limit |
|  | Inverted | 2.960 / 2.847 | 131.617 / 131.322 | 58 | Returned, above error limit |
| Southern containing | Complete | 0.791 / 1.086 | 6.499 / 6.391 | 266 | Returned |
|  | Primary | 1.016 / 0.941 | 14.330 / 12.613 | 195 | Returned, within error limit |
|  | Inverted | 0.886 / 0.853 | 12.404 / 10.152 | 178 | Returned, within error limit |
| Southern displaced | Complete, primary and inverted | Withheld | — | — | Original 96-probe exterior checks passed |

The physical paid runs lost 67 and 64 complete owners respectively. Their 42 and 45 shared owners retained every original NORAD and role. Both paid fits and the complete physical fit used two satellite families. Inverting which antenna measured each singleton changed the horizontal errors by 332 m fixed-zero and 375 m fitted. The earlier same-time one-third packet achieved **0.262 / 0.194 km** with 36 owners through the same full-catalogue route. The larger ownership counts in the mixed physical runs coincided with poorer localization. [Owner overlaps](measurements/mixed-stereo-paid-summary.json) · [Same-time full-catalogue control](full-family-amortized.md)

Both southern paid orientations supplied 205 selected observations. Their paid quadratic graphs yielded 21 and 20 curved tracks and 195 and 186 graph points, compared with 14 curved tracks and 423 graph points for the complete packet. The primary and inverted fits used 12 and 11 families versus seven complete. Both had higher RF residuals. The 195 and 178 published owners shared 80 observations across paid orientations, with no NORAD changes and eight conditional/predictive role changes. Both southern paid publications returned complete 151-point numerical grids. The complete offer returned its 137-point numerical grid. [Graph, native factors and fit receipts](measurements/mixed-stereo-paid.json.gz)

The three southern displaced fits reached the original boundary trigger in both arms. Each receiver separately found the same unique exterior location 50 km beyond the offer, and every check examined 96 probes. The two paid checks took **2.547 and 2.726 CPU seconds**, versus **2.928** with the complete packet. Every branch reached its paired signed gate directly. The three physical fits attempted a warm signed finish and used the original cold signed refit after the warm stationarity check failed. Those costs are charged. No fit invoked the route-level installed fallback. The scorer requires the completed exterior witness as well as the terminal reason, so a direct abstention would fail the displaced-offer screen. [Exact decision receipts](measurements/mixed-stereo-paid.json.gz)

## Charged stage ratios

| Saved offer | Saved solve CPU s, complete / primary / inverted | Saved solve elapsed s, complete / primary / inverted | Acquisition CPU fraction, primary / inverted | Projected acquisition + solve CPU s, complete / primary / inverted | Projected total fraction, primary / inverted |
|---|---:|---:|---:|---:|---:|
| DS30-0016 containing | 2.634 / 2.674 / 2.670 | 2.634 / 2.674 / 2.670 | 0.580 / 0.581 | 9.226 / 6.496 / 6.498 | 0.704 / 0.704 |
| South containing | 2.955 / 3.876 / 3.607 | 2.955 / 3.876 / 3.608 | 0.593 / 0.593 | 12.377 / 9.463 / 9.194 | 0.765 / 0.743 |
| South displaced | 5.807 / 6.201 / 5.721 | 5.807 / 6.202 / 5.722 | 0.593 / 0.593 | 15.229 / 11.788 / 11.308 | 0.774 / 0.743 |

Acquisition CPU uses the saved native timers at each paid antenna slot, holds archived CPU outside those calls fixed and adds measured planning, selection and packet binding of 5–8 ms. The saved solve runs the numerical evidence and all real exterior checks. The projected sums exclude PNG generation and changes in storage waits. The primary masks already spend enough acquisition CPU that halving the complete total would leave **0.791, 0.601 and 2.028 CPU seconds** respectively for the three solves. None of the paid solves fits that allowance. Together with the physical accuracy failure, these two independent gates end this schedule at the saved development cases. [All stage ratios and paired clocks](measurements/mixed-stereo-paid-summary.json)

## Reproduce

Use fresh output paths and `mixed_stereo_paid.py run CASE MODE OUTPUT` for `DS30-0016`, `south-containing` and `south-far`, each with `complete`, `primary` and `inverted`. After sealing all nine files, use `score DIR SUMMARY FULL` under the same lock. The shared rank and release preparation are unchanged, and the scorer checks that the two southern offers use byte-identical respective detector packets. Twenty-seven focused tests passed. [Saved runner](mixed_stereo_paid.py) · [Owned tests](../../../tests/pipeline_eval/test_mixed_stereo_paid.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
lock=/tmp/leo-algo08v2-2x-bench/gauss.lock
flock -x "$lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 90s \
  env PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release:$PWD" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/mixed_stereo_paid.py \
  run "$case" "$mode" "$output"
```
