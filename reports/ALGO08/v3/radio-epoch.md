# Eight-second radio epochs preserve more nominal Doppler information

On DS30-0008, a hindsight design using short radio epochs retained **85.68%** of full nominal horizontal information at a one-third antenna-lane budget. The best measured complete-family design retained **68.62%**. The epoch design narrowly exceeded the complete-family upper bound of **85.42%**, while its own relaxed bound of **96.79%** leaves the 90% target open. The southern epoch mask reached **90.55%** nominally. Both its cold fixed-owner and blind fits missed the containing position screen. The blind omitted fit still withheld through the original exterior check. [Frozen protocol](radio-epoch-protocol.md) · [Saved score](measurements/radio-epoch.json)

## Native costs and geometric opportunity

Each block covers one clock-aligned eight-second epoch on one receiver, channel and exact RF. It pays for every native opportunity in the core, including empty and subsequently unowned lanes. It also pays every original earlier opportunity the installed continuation can consult, up to 12 on that lane within eight seconds. Histories shared across epochs count once. Donor-only rows do not publish a factor. The timeline and every admitted core factor remain in the projected packet. [Block construction](radio_epoch.py) · [Mask and replay boundary](radio_epoch_trial.py)

Selection grants the installed satellite and role labels as a hindsight oracle. Geometry uses the causal current and previous TLEs at the offered center, original RFs and times, nominal 150 Hz noise and phase zero. Measured CFO, geographic references and previous fitted endpoints never enter selection. One clock, receiver and RF-dependent terms, family orbital terms, and original arc offsets remain shared across epoch boundaries wherever applicable. The complete-set position matrices match the archived family experiment. The bounded greedy selector recomputes exact two-arm profile gains for each step's top eight candidates and enforces both receivers, both occupied RF halves, and all occupied time thirds. The independent optimistic bound apportions shared donor costs and allows fractional purchases at fixed nuisance values along 16 directions per arm. [Full matrix and scores](measurements/radio-epoch.json) · [Previous family experiment](arc-design.md)

| Containing recording and design | Paid antenna lanes | Paid stereo visits | Nominal worst-direction information, zero / fitted `c` | Original owned rows in core |
|---|---:|---:|---:|---:|
| DS30-0008, complete family | 4,489 / 13,530 | 3,123 / 6,765 | 68.62% / 68.84% | 1,931 |
| DS30-0008, radio epoch | 4,505 / 13,530 | 3,643 / 6,765 | 85.68% / 85.69% | 1,700 |
| South, complete family | 322 / 2,400 | 161 / 1,200 | 100% / 100% | 266 |
| South, radio epoch | 236 / 2,400 | 146 / 1,200 | 90.68% / 90.55% | 153 |

The dense epoch schedule uses 171 blocks, 3,761 core lanes and 744 additional donor lanes. It publishes 2,226 of 7,016 admitted factors, including 526 outside the original installed owner set. Its paid stereo visits cover **53.85%** of the 6,765 valid visits. The sealed recording counts 6,772 total windows, including seven outside the valid admitted schedule. The one-third budget measures antenna work and can understate tuning, read or other shared visit costs. The southern schedule uses 43 epochs, 168 core lanes and 68 extra donor lanes. It publishes 153 of 456 admitted factors. [Antenna, stereo and RF cost ledger](measurements/radio-epoch.json)

## Owner eligibility and signed replay

The dense epochs intersect 111 original owned arcs. Exact alias and original track eligibility survive for 49 arcs covering 1,245 of 1,700 owned observations. All 296 predictive observations lack an exact original integer alias. Another 159 conditional observations belong to arcs that lost the original curvature check on retained rows. The archive gap and the changed time support preclude a full exact fixed-owner replay. This screen stopped at dense geometry and witness feasibility, which took **6.14 CPU seconds** on saved inputs. [Feasibility by arc and role](measurements/radio-epoch.json) · [Prior dense alias evidence](survey-owner-diagnostic.md)

The southern epochs intersect all 14 original curved arcs. Seven arcs containing 79 paid owner rows lost the original curvature requirement. The cold diagnostic dropped those whole fragments and used the other 74 rows with their witnessed aliases. It cleared ordinary and signed checks in both arms and completed a 165-point numerical grid. The blind signed joint solver received all 153 published factors from the same core, with no imported owner, alias or endpoint information. It published 44 owners and a complete 179-point grid. Both objective replay differences were zero in both fits. [Saved restricted and blind fits](measurements/radio-epoch.json)

| Southern containing fit | Horizontal error km, zero / fitted `c` | RF RMS Hz, zero / fitted `c` | Published owners per arm | Saved solve CPU s |
|---|---:|---:|---:|---:|
| Exact installed v3 | 0.817 / 1.101 | 6.502 / 6.392 | 266 | — |
| Restricted fixed owner and alias | 2.300 / 1.254 | 7.321 / 7.310 | 74 | 1.497 |
| Blind signed joint, same mask | 2.016 / 2.015 | 8.603 / 8.603 | 44 | 4.350 |

The restricted fit missed the 0.25 km limit at zero `c` by worsening 1.483 km. The blind fit worsened 1.199 and 0.914 km, missing in both arms. Fitting `c` lowered the restricted fit's horizontal error by 1.046 km with a 0.011 Hz lower RF RMS. Fitting `c` moved blind error by under one meter and raised RF RMS by less than 0.001 Hz. The restricted time excludes preparation and the oracle design. The blind time includes full preparation, numerical evidence and any fallback. [Paired position and RF measurements](measurements/radio-epoch.json)

The omitted offer reused the exact same projected waveform. The restricted oracle stopped at the original ordinary track gate. The blind signed replay returned `both_receivers_support_far_exterior` in **5.788 CPU seconds**. Neither blind invocation triggered fallback. The blind route isolates what the solver can do without owner labels after paying for an owner-informed mask. The selection rule itself requires hindsight support. This experiment measured saved computations and leaves detector implementation, acquisition speed and a deployable selector untested. [Paired mask identity and route charges](measurements/radio-epoch.json)

## Reproduction

Run the pinned payload under the low-priority Gauss lock. Run `geometry-fit south-containing` first, then `geometry-fit south-far` with `--design-path "$out/south-containing.json"`. Run `blind` for the two southern offers with that same containing receipt, saving their outputs as `$case-blind.json`. Run `geometry-fit DS30-0008` once. Run `radio_epoch_score.py "$out" "$out/score.json"` on the same worker with the repository and its `src` on `PYTHONPATH`. Six focused tests passed. [Owned tests](../../../tests/pipeline_eval/test_radio_epoch.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
code="$PWD/reports/ALGO08/v3"
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$code:$payload:$release/src:$release" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs "$code/radio_epoch_trial.py" \
  "$mode" "$case" "$destination"
```
