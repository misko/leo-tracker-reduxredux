# Partner-on-hit confirmation on fourteen disjoint roof recordings

The holdout is the exact complement of the eight discovery recordings within the authenticated 22-recording fixed-four roster. The fourteen cases include both earlier roof archives and the two later lower-edge cases. Each case keeps its original capture identity, causal catalogue, tracking configuration and offered tile. The fixed rule and source hashes were frozen before the new position results. The pooled panel preserves each original discovery row and adds the fourteen fresh rows. [Prospective plan](plan.json) · [Prediction lock](prediction-lock.json)

At each valid visit, the physical primary alternates independently at each recorded RF. The primary contributes its full fixed-four candidate list. The partner contributes its full list after a strict primary fractional-gate hit, with an empty physical slot otherwise. The source audit reproduces the alternating-primary and partner-on-miss inputs byte for byte from the same complete stock factors. The four policy cells therefore isolate co-observed partner gates and partner-only gates under the frozen detector and numerical receiver. All comparisons use `c = 0` and fitted `c` on the matched physical inputs. [Packet and observation audit](packet-audit.json) · [Call counts](support.csv)

The newly measured resources cover stored native factors through both position arms on CPUs 6–9, one thread, 512 MiB, zero swap and a per-case 210 s service limit. Detector calls are schedule counts. The original eight resource measurements remain marked as discovery. The 5% and 10% one-sided position allowances use the original-v5 no-repair reference and fixed-four stock as distinct comparators. [Resources](resources.csv) · [Per-case scores](scores.csv) · [Capture-era v5 roles](capture-era-v5.csv)

The geographic and conditional RF contrasts report the effect of adding co-observed support with partner-only support present or absent, the effect of adding partner-only support under both choices, and the difference between those paired effects. [Per-case effects](effects.csv) · [Effect summary](effects-summary.csv) · [Holdout and pooled charts](charts/README.md)

## Holdout results

All fourteen new fits returned coordinates in both arms. Adding co-observed partner hits to primary-only support improved 11 of 14 positions at `c = 0` and 10 of 14 with fitted `c`. The median paired error changes were −263 m and −222 m. When partner-only observations were already present, adding the co-observed hits improved 10 and 11 of 14 positions, with median gains of 143 m and 147 m. Adding partner-only observations after the co-observed hits increased median error by 32 m and 44 m, with four and six improvements respectively. [Paired effects](effects-summary.csv)

Each divided table entry lists `c = 0` / fitted `c`. The allowances count positions up to 5% or 10% above the original v5 no-repair error on the same recording.

| Holdout condition | Median error, km | P95 error, km | Within 5% of v5 | Within 10% of v5 | Median conditional RF RMS, Hz |
| --- | ---: | ---: | ---: | ---: | ---: |
| Alternating primary only | 0.748 / 0.687 | 1.760 / 1.758 | 7 / 7 | 7 / 7 | 90.523 / 90.370 |
| Partner on hit | 0.742 / 0.688 | 2.424 / 2.405 | 9 / 10 | 11 / 10 | 89.756 / 89.751 |
| Partner on miss | 0.811 / 0.788 | 1.461 / 1.475 | 10 / 10 | 10 / 10 | 93.652 / 93.617 |
| Both stock lanes | 0.774 / 0.765 | 1.517 / 1.375 | 11 / 11 | 12 / 11 | 92.906 / 92.868 |

DS26-0168 drove the upper tail. Its fitted error was 1.800 km with primary only, 4.154 km after adding the co-observed partner, and 0.796 km after also keeping the partner-only observations. On the holdout, partner-on-hit beat the stock median in both arms while its P95 was 0.907 km and 1.030 km higher. Relative to primary-only, adding co-observed hits lowered conditional RF RMS by median paired changes of 1.09 Hz and 1.06 Hz. Adding partner-only observations afterward raised it by 0.59 Hz and 0.66 Hz. The holdout services took 35.5–135.6 s, with median wall and CPU times of 72.0 and 51.3 s. Peak cgroup memory reached 404.5 MiB with zero swap. [Per-case scores](scores.csv) · [Resources](resources.csv)

## Pooled baseline

The 22-case pooled median errors for primary-only, partner-on-hit, partner-on-miss and both stock lanes were 0.855 / 0.815, 0.717 / 0.732, 0.867 / 0.893 and 0.774 / 0.776 km. Partner-on-hit met the original v5 10% allowance on 15 and 13 of 22, while stock met it on 13 of 22 in both arms. Partner-on-hit P95 was 2.241 / 1.946 km, versus 1.543 / 1.437 km for stock. Across 22 recordings, the four policies schedule 146,268, 193,967, 244,837 and 292,536 lane calls and retain 47,699, 79,022, 63,982 and 95,305 gated observations respectively. [All methods and allowances](summary.csv) · [Support census](support.csv)

## Reproduction

Run `python -m tools.pipeline_eval.qualification.partner_holdout /path/to/new/local/work` from a checkout with the original authenticated fixed-four archives and without an existing holdout plan. After the terminal prediction seal is created, run `python -m tools.pipeline_eval.qualification.partner_holdout_results /path/to/work --plot /path/to/plots`. The candidate-only `positions.jsonl.gz` keeps every pooled terminal outcome, and both matched chart archives include the three independently measured comparator endpoints.
