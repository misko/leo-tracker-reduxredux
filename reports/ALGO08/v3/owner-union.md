# Keeping the original solver owners across a full recording

Keeping every originally owned signed factor took DS30-0008 from **7,016 to 4,472** solver inputs, but a fresh installed-v3 solve retained only **4,341 owners per arm**. The 4,341 kept their original satellites. Horizontal error rose **70 m** at fixed zero and **107 m** with fitted `c`. The same test preserved both southern terminal decisions, including withholding outside the offered region. Charging the dense replay for the complete original continuation history gives a projected **79.27 CPU seconds before publication**. Even the idealized donor floor gives **64.10 seconds**, versus the historical half-time CPU budget of **55.54 seconds**. [Frozen protocol](owner-union-protocol.md) · [Saved comparisons](measurements/owner-union.json)

## What the oracle supplied

The mask contains the union of the installed full-v3 owners in the two calibration arms. It preserves the signed carrier and fractional timing, gate values, rank, clock and every admitted probe's metadata. It sets other candidate arrays to empty and binds the changed analysis stream to a new digest. The masked solver receives observation bytes, the original causal TLE archive and the same region. The original ownership labels are used for the hindsight selection and postfit comparison. They never enter track building, association or position fitting. The omitted southern offer uses the containing waveform's same mask because the original omitted decision withheld both arms. [Exact mask and replay](owner_union_trial.py) · [Canonical owner join](primary_owner_census.py)

The preceding 128-visit experiment kept all 25 originally owned prefix factors using native verification and continuation. All 25 were primaries. The full dense owner union includes **4,233 primary and 239 residual factors**. Earlier full-record interleaves did not select the owner union. One earlier saved mixture restricted the solver to a different sampled RF membership. This replay isolates what happens when every originally owned factor is supplied exactly and previously unowned inputs disappear. [Prefix timings](primary-schedule.md) · [Interleave experiments](aperture.md)

## Track discovery and scientific decisions

| Input | Factors, full → owner union | Graph tracks, full → owner union | Curved tracks / points, full → owner union | Full → owner-union solver CPU s | Terminal |
|---|---:|---:|---:|---:|---|
| DS30-0008 | 7,016 → 4,472 | 236 → 134 | 111 / 4,522 → 79 / 3,508 | 54.720 → 29.453 | Both returned, changed owners and evidence |
| Southern containing | 456 → 266 | 30 → 14 | 14 / 266 → 14 / 266 | 4.758 → 4.504 | Exact original decisions and evidence |
| Southern omitted | 456 → 266 | 30 → 14 | 14 / 266 → 14 / 266 | 6.274 → 5.530 | Exact original exterior withholding |

Of the 4,472 dense masked inputs, 4,372 entered Graph tracks. The fresh solve lost 100 original owner observations during track preparation and another 31 after track preparation. It returned a complete 179-point position grid and zero selected-objective replay difference in each arm. The two arm endpoints, owner digests, path and grid values changed. The southern containing run reconstructed both original 266-owner maps and the complete 137-point grid with zero replay difference. The omitted offer returned the original `both_receivers_support_far_exterior` reason. [Preparation and ownership evidence](measurements/owner-union.json)

| Input | Horizontal error km, `c = 0` / fitted, full → owner union | RF RMS Hz, `c = 0` / fitted, full → owner union |
|---|---:|---:|
| DS30-0008 | 1.639 / 1.512 → 1.709 / 1.619 | 129.703 / 129.663 → 128.280 / 128.236 |
| Southern containing | 0.817 / 1.101 → 0.817 / 1.101 | 6.502 / 6.392 → 6.502 / 6.392 |
| Southern omitted | — | — |

The dense RF RMS fell on the smaller support while geographic error increased. Within the owner-union dense fit, enabling fitted `c` on the same support lowered RMS by 0.044 Hz and error by 91 m. In the southern containing fit it lowered RMS by 0.110 Hz and increased error by 285 m. Geographic references enter only in postfit scoring. [Physical reference](../../2026_11_21_ds30_full/reference-audit.json) · [Southern reference](../regional-release/scoring-key.json) · [Postfit scorer](owner_union_score.py)

## Original continuation and the call budget

The guaranteed history schedule charges full detector calls on each retained antenna lane and its entire original 12-slot same-receiver, channel and RF history within eight seconds. It keeps all other timeline slots, including empty ones. This reproduces every prior detector factor the installed continuation could see on a retained lane in a hypothetical native replay. The necessary count grants all preceding opportunities compatible factors and demands three prior opportunities including one at least 0.4 seconds old. The intermediate estimate runs the stock slope-vote logic on the available post-continuation single factors. It finds a witness for 4,054 dense and 224 southern retained selections, and charges the complete preceding window for the other 418 and 42. The complete installed raw competing-factor ledger is unavailable. The intermediate estimate cannot guarantee which carrier would win in the original two-scan verifier and continuation. [Per-antenna and RF geometry](measurements/owner-union.json) · [Earlier whole-scan ledger limitation](anchor-orbit-census-protocol.md)

| Required native call geometry | Dense antenna lanes of 13,530 | Southern antenna lanes of 2,400 | Dense projected acquisition CPU s | Dense acquisition plus measured masked solve CPU s |
|---|---:|---:|---:|---:|
| Retained factors alone | 4,472 | 266 | 33.96 | 63.42 |
| Necessary ideal donor count | 4,719 | 308 | 34.65 | 64.10 |
| Archived exported-factor witnesses with full-window charges on unresolved lanes | 6,170 | 322 | 38.65 | 68.10 |
| Complete original donor windows | 10,218 | 322 | 49.82 | 79.27 |

The CPU projection uses the measured 37.34 seconds across all dense native callbacks, prorated by antenna lane, and retains 21.62 seconds outside those callbacks. Per-lane costs may differ with factor content and RF. The first row omits donor costs to show the optimistic limit. The dense branch missed the exact scientific and CPU screens, ending the experiment before the signed-enabled joint route. The southern replay provides an exact control at one independent site and two offers. Neither calculation measures raw acquisition elapsed time or PNG publication. [Dense measured acquisition split](acquisition-split.md) · [Historical CPU target](first-55/stage-clocks.csv)

The solver clocks come from fresh low-priority saved replays ending after numerical evidence. Full solver clocks come from the archived matching installed-v3 packets. Fresh full-input preparation supplied the comparison Graph counts for each offer. Four owned tests and four adjacent continuation tests passed. [Replay driver](owner_union_trial.py) · [Tests](../../../tests/pipeline_eval/test_owner_union_trial.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
trial_code="$PWD/reports/ALGO08/v3"
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$trial_code:$payload:$release/src:$release" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs "$trial_code/owner_union_trial.py" \
  "$case" "$new_receipt"
```

Use `DS30-0008`, `south-containing` and `south-far`. For each case, run once with `--prepare-only` to collect the original Graph comparison, then run without that option for the masked solve.
