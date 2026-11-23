# Signed carrier precision on saved full-coverage inputs

Snapping the saved carrier readout to either **610.3515625 Hz** or **152.587890625 Hz** failed the prespecified DS30-0008 position screen in both calibration arms. All 7,016 admitted detector factors remained available. The quarter-bin solve retained 4,400 owners per arm and fit the RF observations within 136.2 Hz RMS. Its horizontal errors nevertheless rose to **3.000 km at zero `c` and 2.811 km with fitted `c`**, versus 1.086 and 1.080 km for the archived exact-CFO signed solve. The two synthetic spacings both preserved exterior withholding on the southern omitted offer. [Frozen protocol](carrier-grid-protocol.md) · [Numeric receipt](measurements/carrier-grid.json)

## Placement

The installed timing-first receiver uses a 10 MHz sample clock, stride four and 4096 coarse bins. The native bin indices are signed and the mixing center is set from the two search bounds. The exported fractional tracking CFO is in signed baseband Hz after coarse acquisition, mixing-center restoration and fine verification. This screen snapped each pre-existing exported CFO to the nearest point on a **zero-centered** lattice, with midpoint ties to even. It preserved admissions, candidate rank, verification margins, full fractional timing and every empty window. The two southern offers used byte-identical transformed observations for each spacing. The signed joint route kept the same repair, exterior veto, numerical grid and installed-v3 fallback. Geographic references and baseline owner labels were used only to score the completed replays. [CFO field and native source checks](carrier_grid_trial.py) · [Carrier binary provenance](carrier-fft-bound.md)

| Recording | Spacing | Factors changed / admitted | Median / p95 absolute change Hz | Maximum absolute change Hz |
|---|---|---:|---:|---:|
| DS30-0008 | Full bin | 7,016 / 7,016 | 152.74 / 290.05 | 305.14 |
| DS30-0008 | Quarter bin | 7,016 / 7,016 | 37.51 / 72.49 | 76.29 |
| South, both offers | Full bin | 456 / 456 | 160.56 / 288.48 | 304.75 |
| South, both offers | Quarter bin | 456 / 456 | 37.57 / 71.45 | 76.02 |

## Position, frequency fit and publication

| Containing offer | CFO input and solver | Horizontal error km, zero / fitted `c` | RF RMS Hz, zero / fitted `c` | Published owners per arm | Accuracy screen |
|---|---|---:|---:|---:|---|
| DS30-0008 | Exact installed v3 | 1.639 / 1.512 | 129.703 / 129.663 | 4,472 | Reference |
| DS30-0008 | Exact signed joint | 1.086 / 1.080 | 128.821 / 128.753 | 4,440 | Reference |
| DS30-0008 | Full-bin signed joint | 2.560 / 2.402 | 201.772 / 201.736 | 4,069 | Fail both arms |
| DS30-0008 | Quarter-bin signed joint | 3.000 / 2.811 | 136.235 / 136.231 | 4,400 | Fail both arms |
| South | Exact installed v3 or signed joint | 0.817 / 1.101 | 6.502 / 6.392 | 266 | Reference |
| South | Full-bin signed joint | 1.640 / 1.283 | 166.530 / 166.228 | 412 | Fail at zero `c` |
| South | Quarter-bin signed joint | 0.960 / 0.846 | 40.034 / 40.063 | 418 | Pass position |

On dense input, fitted `c` lowered horizontal error by 158 m on the full bin and 189 m on the quarter bin. It lowered RF RMS on the same admitted observations by 0.036 and 0.004 Hz. On the southern quarter bin, fitted `c` lowered position error by 113 m while raising RF RMS by 0.029 Hz. The full-bin southern error decreased by 357 m and the RF RMS decreased by 0.302 Hz. The southern omitted reference lay 52.5 km beyond the nearest offer face. Both placements consistently returned `both_receivers_support_far_exterior` with both arms empty. All successful solves produced complete numerical grids and a zero selected-objective replay delta in each arm. The dense grids each evaluated 179 points. The southern full-bin and quarter-bin grids evaluated 172 and 151 points, respectively, compared with 137 on exact CFO. [Paired endpoints, RF, evidence and digests](measurements/carrier-grid.json) · [Exact signed baseline](measurements/blind-joint-signed.json.gz)

## Track and owner changes

| Recording | CFO input | Graph tracks | Curved tracks / points | Kept / lost / added / relabeled owners versus installed v3, per arm |
|---|---|---:|---:|---:|
| DS30-0008 | Exact | 236 | 111 / 4,522 | — |
| DS30-0008 | Full bin | 209 | 100 / 4,445 | 3,640 / 827 / 424 / 5 |
| DS30-0008 | Quarter bin | 223 | 109 / 4,599 | 4,113 / 359 / 287 / 0 |
| South, containing | Exact | 30 | 14 / 266 | — |
| South, containing | Full bin | 24 | 21 / 395 | 262 / 4 / 150 / 0 |
| South, containing | Quarter bin | 24 | 22 / 418 | 266 / 0 / 152 / 0 |

The dense signed owner map digests changed in both placements. Its exact archive retains counts, digests and aggregate overlap with installed v3. Per-observation dense overlap uses the available installed-v3 owner map keyed by stable observation ID. The exact southern signed and installed-v3 map digests agree, so the southern overlap applies to both originals. Dense RF and position effects varied with which tracks and owners survived, even though the admitted detector set and rank were fixed. [Stable observation ID join](carrier_grid_score.py) · [Exact Graph baseline](measurements/owner-union.json)

## Charged saved solver CPU

| Offer | Exact installed v3 s | Exact signed joint s | Full-bin signed joint s | Quarter-bin signed joint s |
|---|---:|---:|---:|---:|
| DS30-0008 | 54.515 | 38.062 | 32.416 | 33.686 |
| South, containing | 4.523 | 3.849 | 4.821 | 4.291 |
| South, omitted | 6.387 | 6.429 | 6.878 | 7.500 |

No route invoked fallback. The scientific gates accepted the four localization runs and withheld both omitted runs, so those gates did not flag the dense accuracy losses. Each transformed row is one fresh saved solve through full numerical evidence or withholding. The original clocks are historical. The current runner uses the archived route's default start and repair, with later optional proposal hooks disabled. It also records Graph group membership during preparation. The timings include attempted work and fallback when invoked. They exclude raw acquisition and PNG publication. [Timings and signed route outcomes](measurements/carrier-grid.json) · [Exact signed replay](blind-joint-signed.md)

The treatment grants exact detector admission, candidate rank, timing, continuation and the nearest bin to the original fine estimate. It measures the solver's response to CFO precision under those assumptions. Performance, peak errors, timing movement and selection changes from a real cheaper receiver remain unmeasured. This screen ended with the two dense solves and the four southern solves.

## Reproduction

Use the installed payload and release environment below once per case and spacing. Cases are `DS30-0008`, `south-containing` and `south-far`. The spacing names are `bin` and `quarter`. Save the results as `$case-$mode.json` in a new directory. Run `carrier_grid_score.py <directory> <receipt.json>` under the same worker constraints with the repository checkout and its `src` on `PYTHONPATH`. Six focused tests passed, including two signed-route tests. [Owned tests](../../../tests/pipeline_eval/test_carrier_grid_trial.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
trial_code="$PWD/reports/ALGO08/v3"
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$trial_code:$payload:$release/src:$release" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs "$trial_code/carrier_grid_trial.py" \
  "$case" "$mode" "$new_output"
```
