# Full-catalogue signed solves on complete and paid packets

Keeping the full causal catalogue restored the paid DS30-0016 fix. The direct signed solve took **2.574 CPU seconds**, kept **36 owners** in each calibration arm and returned errors of **0.262 / 0.194 km** for `c = 0` and fitted `c`. The restricted family pool kept 18 and returned **8.623 / 8.621 km** on the identical paid receiver packet and quadratic graph. The full-catalogue result came within 15 m of the archived full signed paid result in both arms, with the same owner hashes and with both original RF and geometry qualifications. [Frozen protocol](full-family-amortized-protocol.md) · [Paired measurements](measurements/full-family-amortized-summary.json) · [Sealed runs](measurements/full-family-amortized.json.gz)

On DS30-0008 the full catalogue returned the original full-signed **4,440 owners and roles** with errors of **1.088 / 1.079 km** in **28.680 CPU seconds**. The smaller certified pool used 25.661 CPU seconds and returned 1.464 / 1.506 km on that packet. The representative-time certificate left both full-catalogue publications unchanged, but it failed the exact cold-rank gate and saved no measurable ranking time. [Earlier certified pool](certified-salvage.md) · [Earlier paid crossover](paid-certified.md)

## Full-catalogue route

Both fresh variants use the released centre seeds and regional corners, original candidate order and three full-time finalists. They share the same exact earlier centre preparation, same full-catalogue salvage with interval pruning, confidence elision, paired signed refit, original exterior check and complete numerical grid. On paid DS30-0016 beyond the full-catalogue rank, all 49 original curved points entered the first gate, 29 survived and seven predictive points qualified. The ordinary and warm signed pair passed without route fallback. On complete DS30-0008 the bounded ordinary recovery removed five incompatible tracks, then the warm signed pair passed. The endpoints for both cases were inside the exterior trigger, so none of the four runs needed external probes. Both cases published complete 179-point numerical grids using both calibration arms. [Full route and ordered observations](measurements/full-family-amortized.json.gz)

| Saved input and comparator | Solve CPU s | Position error, zero / fitted (km) | Frequency RMS, zero / fitted (Hz) |
|---|---:|---:|---:|
| DS30-0008 full, installed v3 | 60.966 | 1.639 / 1.512 | 129.703 / 129.663 |
| DS30-0008 full, earlier full signed | 39.045 | 1.086 / 1.080 | 128.821 / 128.753 |
| DS30-0008 full, earlier certified pool | 25.661 | 1.464 / 1.506 | 129.457 / 129.444 |
| DS30-0008 full, full-catalogue certified finish | **28.680** | **1.088 / 1.079** | **128.822 / 128.753** |
| DS30-0016 paid, earlier full signed | 2.968 | 0.247 / 0.182 | 121.482 / 121.379 |
| DS30-0016 paid, earlier certified pool | 4.365 projected | 8.623 / 8.621 | 112.389 / 112.390 |
| DS30-0016 paid, full-catalogue certified finish | **2.574** | **0.262 / 0.194** | **121.487 / 121.383** |

The paid certified pool comparison uses its separately audited released-preparation projection. Its sealed fitted clock includes the original bare-preparation instrumentation. The full-catalogue route's saved solve clock measures the released preparation and charged evidence directly. The comparison holds the original detector observations fixed within each case and excludes acquisition, PNG generation and new recordings. [Paid clock adjustment](measurements/paid-certified-preparation.json) · [Published paired outcomes](measurements/full-family-amortized-summary.json)

## What representative observation pairs can prove

For any two samples of one track, the minimum summed squares after allowing an unconstrained common offset is half the squared difference between their raw frequency residuals. The satellite's native alias and the Gaussian track bias are common within those samples, so both cancel in this difference. Summing over disjoint pairs gives a lower bound with every omitted nonnegative residual square left free. The prototype uses at most eight pairs distributed over the original track. It prunes a candidate only when the outward-padded bound exceeds a full-time incumbent upper bound and independently forces its original RMS past 450 Hz. The existing all-time visibility check can eliminate an invisible candidate. Every visible unresolved candidate goes through the original multi-observation profile and gates. The stock row-zero fallback remains present, and ties and unsupported domains replay the full original profile. [Contrast certificate](representative_contrast_bound.py)

| Saved input | Catalogue work before proof | Removed by exact visibility | Removed by contrast | Profiled after proof | Association CPU s, control → contrast | Rank CPU s, control → contrast | Complete CPU s, control → contrast |
|---|---:|---:|---:|---:|---:|---:|---:|
| DS30-0008 full | 2,621,376 | 1,838,078 | 772,869 | 10,429 | 1.865 → 1.747 | 5.085 → 5.106 | 28.680 → 28.642 |
| DS30-0016 paid | 92,736 | 47,739 | 21,614 | 23,383 | 0.026 → 0.028 | 0.123 → 0.128 | 2.574 → 2.625 |

Even after discarding **99.6% of full profiles** on the dense input, the association stage still pays for all-catalogue orbit planes, track gathers, visibility, representative differences and bound checks. Erasing the entire baseline association stage for free would leave **26.815 seconds** for the complete dense solve. Its cold stage costs 12.265 CPU seconds, including roughly 7.18 outside rank, and its numerical evidence costs another 6.452 seconds. The earlier shared-anchor approach already removes repeat projections. Earlier Doppler moment interpolation changed 12 dense assignments, and its exact streamed follow-up saved only about 12 ms on the short physical recording. [Earlier shared anchor work](blind-rank.md) · [Moment and streamed controls](../single-core-2x/solver-streamed-nomination.md)

The contrast prototype preserved the complete ordered NORAD and integer alias lists, all three full-time finalist scores and selected locations and phases, and the final owners, qualifications, RF values, endpoints, exterior outcomes and numerical evidence digests in both new pairs. It changed the cold diagnostic row hashes. A direct unit control reproduced a 4.97 × 10⁻¹⁴ Hz difference when the same original NumPy profile used a narrower Fortran-layout column stride across candidate rows. The frozen equivalence gate includes those diagnostics, so the contrast prototype failed the gate. This effect and the measured stage ceiling ended the prototype at the two primary cases. [Equivalence and timing receipts](measurements/full-family-amortized.json.gz) · [Component tests](../../../tests/pipeline_eval/test_representative_contrast_bound.py)

## Reproduce

Use an empty output directory and run `full_family_amortized_trial.py run CASE MODE OUT` for `DS30-0016` and `DS30-0008`, with `control` then `contrast` for each. Use `score DIR SUMMARY FULL` after all four receipts are sealed. The fit runner obtains the already sealed full and paid detector packets without regenerating receiver data. The `control` path runs exact unpruned nomination through the shared-centre rank. Twenty-five focused and adjacent tests passed, including the certificate, exact matched gates, row-zero handling and an audit that detects changes to ranked diagnostics. [Fit runner](full_family_amortized_trial.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
lock=/tmp/leo-algo08v2-2x-bench/gauss.lock
flock -x "$lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 125s \
  env PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release:$PWD" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/full_family_amortized_trial.py \
  run "$case" "$mode" "$output"
```
