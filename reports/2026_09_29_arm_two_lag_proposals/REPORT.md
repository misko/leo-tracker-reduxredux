# Full-cohort two-lag quality audit

All three exploratory two-lag variants were evaluated on the complete frozen
704-dwell host cohort with the frozen fused-V4 reference and omit-power
proposal feature rows. Each returned all 15,488 receiver-window rows and
123,904 final candidate entries. This report compares recovery only; it makes
no host-runtime comparison.

| retained lags | recovered standard hits | recovery | native positive hits |
| --- | ---: | ---: | ---: |
| lag1 + lag3 | 19,188 / 19,581 | 97.9930% | 39,811 |
| lag1 + lag5 | **19,189 / 19,581** | **97.9981%** | 39,764 |
| lag3 + lag5 | 19,160 / 19,581 | 97.8500% | 39,698 |

`lag1 + lag5` is the best quality result in this exploratory comparison. It
is 45 recovered hits below the sealed three-lag resampled omit-power cohort
(19,234 / 19,581). Its per-rate recovery is 4,513/4,573 at 2.5 Msps,
5,357/5,466 at 5 Msps, 5,086/5,186 at 7.5 Msps, and 4,233/4,356 at 10 Msps.

These three variants were selected after a small 32-dwell exploratory audit;
the full cohort is therefore not a holdout. The outputs and audits are sealed
under `host704-lag1_lag3`, `host704-lag1_lag5`, and `host704-lag3_lag5`.
