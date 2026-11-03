# DS28 revision 2 — algorithm comparison results

The additional residual search improves fitted-c mean position error from **820.7 to 802.5 m** across 14 usable scans. It recovers **57 native GLRT points in two scans**. All four research variants produce the same accepted associations and position errors within 0.001 m. Expanding TLE age, expanding phase, and applying the tested recency penalty provide no incremental accuracy benefit on this cohort.

## Coverage and matched comparison

DS28 revision 2 has 16 fast, 10 Msps acquisitions: eight retained and eight newly added. Fourteen have usable baseline inputs, comprising seven retained and seven new scans. DS28-0001 retains its upstream ALGO02 discovery failure; DS28-0016 has no published GLRT input at the census. Both remain in every method's roster, with unknown position error and association rather than zeros. Availability is **14/16 (87.5%)**.

The baseline is the deployed ALGO05 installation. All 14 fresh replays exactly match the published production decisions, positions and candidates. Earlier acquisition/GLRT/ALGO04 evidence is reused through public exports; this is a conditional recovery comparison, not a fresh IQ extraction or cold regional rerun. Ground truth enters reporting only after inference is sealed. All inference TLEs are causal.

| Method, fitted c | Mean error, m | Median, m | P90, m | Worst, m | GLRT associated | Added points |
|---|---:|---:|---:|---:|---:|---:|
| Current ALGO05 | 820.7 | 725.7 | 1,433.6 | 1,769.8 | 74.855% | 0 |
| 48 h / ±15 s recovery | 802.5 | 725.7 | 1,433.6 | 1,769.8 | 74.969% | 57 |
| 72 h / ±15 s recovery | 802.5 | 725.7 | 1,433.6 | 1,769.8 | 74.969% | 57 |
| 72 h / ±30 s recovery | 802.5 | 725.7 | 1,433.6 | 1,769.8 | 74.969% | 57 |
| 72 h / ±30 s + recency | 802.5 | 725.7 | 1,433.6 | 1,769.8 | 74.969% | 57 |

Association increases from **37,464/50,049** to **37,521/50,049**. Two scans improve; none worsen. The count within 500 m remains **6/14 (42.9%)**, and five scans remain above 1 km. The median and upper tail do not improve.

![Position-error distributions with matched c arms](position_error_distributions.png)

![Per-scan errors and association](per_scan_results.png)

## Separate the new scans from the original cohort

| Subset, fitted c | Usable / members | Baseline mean, m | Recovery mean, m | Baseline median, m | Recovery median, m | GLRT before → after |
|---|---:|---:|---:|---:|---:|---:|
| Original revision 1 | 7/8 | 652.8 | 650.4 | 480.8 | 480.8 | 75.528% → 75.629% |
| Newly added in revision 2 | 7/8 | 988.7 | 954.6 | 1,213.4 | 1,103.4 | 74.019% → 74.149% |
| Entire revision 2 | 14/16 | 820.7 | 802.5 | 725.7 | 725.7 | 74.855% → 74.969% |

The larger cohort's higher mean relative to revision 1 reflects the newly added, harder scans. The matched comparison uses the same scans for every method. All four recovery variants are equivalent at the table's precision.

| New scan | Baseline fitted-c error, m | Recovery error, m | GLRT before → after |
|---|---:|---:|---:|
| DS28-0009 | 115.7 | 115.7 | 76.81% → 76.81% |
| DS28-0010 | 578.7 | 578.7 | 78.89% → 78.89% |
| DS28-0011 | 1,213.4 | 1,213.4 | 77.58% → 77.58% |
| DS28-0012 | 1,769.8 | 1,769.8 | 74.06% → 74.06% |
| DS28-0013 | 1,464.4 | 1,464.4 | 64.43% → 64.43% |
| DS28-0014 | 437.2 | 437.2 | 64.65% → 64.65% |
| DS28-0015 | 1,341.5 | **1,103.4** | 75.11% → **76.35%** |
| DS28-0016 | Unavailable | Unavailable | Unknown |

## Recovered evidence

| Scan | Source | Satellite | Added points | Causal TLE age | Fitted-c error before → after |
|---|---|---:|---:|---:|---:|
| DS28-0002 | RX2 CH6 | 64147 | 28 | 14.72 h | 294.3 → 277.7 m |
| DS28-0015 | RX1 CH1, 277.48–299.82 s | 64182 | 29 | 20.79 h | 1,341.5 → 1,103.4 m |

The new recovery in DS28-0015 reduces error by **238.1 m (about 18%)**. Its screening identity margin exceeds 66 across all tested partitions and c arms. The fitted phase is approximately zero and the physical, bias-profiled RMS is 56.2 Hz with fitted c and 55.3 Hz with c=0. All existing candidate, control, ownership, exact-orbit and quadrature checks pass.

The c=0 error independently improves from **1,306.3 to 1,083.7 m**, a 222.7 m reduction. No-addition controls remain within 0.01 m of the saved baseline, so these improvements are not due simply to continuing the optimizer.

![Newly recovered source, corrected orbit and residual](curves/DS28-0015.png)

**Residual limitation:** the plotted residual is not demonstrably white noise. It has an early/late signed pattern: the first temporal half averages −22.6 Hz and the second +34.5 Hz; a diagnostic straight-line fit has slope about +5.12 Hz/s. It passes the current compatibility gates, but this visible structure deserves review before treating the result as promotion-ready. The fixed experiment was not retuned after evaluating GPS error.

## Controlled c ablation and frequency evidence

With **c=0**, whole-cohort mean error changes **829.6 → 812.3 m**; the median stays 729.1 m and P90 stays 1,447.0 m. For the newly added scans alone, mean error changes **993.3 → 961.4 m**. The same 57 observations are recovered, with the same candidate sets and search budgets.

Frequency-fit effects are separate from position accuracy. On matched baseline support, the recorded fitted-c negative-twice-ELBO averages 1.19 higher than c=0, despite its lower mean geographic error. This is a penalized objective, not raw RMS. Absolute objectives before and after adding points have different observation support and should not be used as localization gains. See `frequency-fit-ablation.json`, `trials.csv`, and the native residual figures.

## Rejected or deferred evidence

- **DS28-0010:** 29 RX1/CH4 points nominate NORAD 67579 at ±15 s. Candidate and control fitted-c optimizers do not declare convergence, so the baseline is retained. At ±30 s, the full-data identity remains 67579, but held-out partitions prefer NORAD 66201 at roughly −15.7 to −15.8 s. Margins fall below the fixed threshold of 10 and identity stability fails. The expanded search exposes ambiguity; it does not justify forcing an association.
- **DS28-0009:** a 59-point RX1/CH6 fragment nominates existing family 63805. Existing-family extension is unchanged by these research variants, so no new points are adopted.
- **DS28-0013:** a 57-point RX1/CH6 fragment similarly nominates existing family 62199. It remains outside this new-family recovery comparison.
- **DS28-0001:** the public input matches the earlier bounded retry, which failed with `orbit phase interpolation never extrapolates` during regional discovery. That verified historical failure evidence is retained; the identical retry was not repeated.

## Interpretation and validation

The simplest 48 h / ±15 s additional residual search obtains all measured gains. There is no incremental evidence here for widening the age/phase bounds or adding the tested recency penalty. Keep production unchanged while reviewing the residual structure in 0015 and the optimizer/control behavior in 0010. The unchanged worst error is DS28-0012 at 1.770 km; DS28-0013 remains at 1.464 km and has an existing-family extension hypothesis worth investigating.

This is a small, single-site evaluation and does not establish a general 500 m accuracy result or globally unique satellite identities. The search examines the three longest eligible residual fragments per scan, 34 fragments in total, with a bounded candidate shortlist.

All **140 scan × method × c-arm rows** pass integrity and ownership checks. All 14 baseline likelihoods and ownerships replay exactly, and all 14 match public production outcomes. The causal audit verifies 20,955 unchanged nominal TLEs. **26 tests pass** across dataset revision identity, screening, normalized evidence, physical mixtures and phase uncertainty. The underlying numerical source hashes remain unchanged through evaluation.

See [complete method report](README.md), [all subset statistics](subset-statistics.csv), [per-scan results](position-errors.csv), [candidate curves](CURVES.md), and [validation receipt](validation.json). Production was not modified.
