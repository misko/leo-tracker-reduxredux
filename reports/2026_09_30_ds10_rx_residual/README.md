# Candidate-specific cross-receiver residual transfer also appears in DS10

Same-candidate slopes from the opposite receiver improve held residual prediction on **430 of 696 supported tracks**, with **7.740 Hz median paired reduction** in absolute residual error. A matched other-candidate control worsens prediction. This extends the prior DS7–9 observation to DS10, but does not establish a receiver calibration, true satellite identity, or improved position accuracy.

| Population / predictor | Cases | Improvements | Median paired held-error reduction |
|---|---:|---:|---:|
| Supported targets, same-candidate opposite RX | 696 | 430 | +7.740 Hz |
| RX0 targets, same-candidate opposite RX | 341 | 215 | +8.977 Hz |
| RX1 targets, same-candidate opposite RX | 355 | 215 | +7.124 Hz |
| Matched targets, same-candidate opposite RX | 132 | 79 | +7.758 Hz |
| Same matched targets, other-candidate opposite RX | 132 | 49 | −11.103 Hz |

On the matched population, same-candidate prediction beats the other-candidate control in **98/132** cases, with a median paired advantage of **21.019 Hz**. These are medians of per-track median absolute held errors after training-derived offsets, not normalized mixture scores or absolute Doppler errors against truth.

![Per-scan and matched residual transfer](transfer.png)

All 24 scans contain supported targets, and 21/24 have positive median gains. The average of the per-scan mean gains is +17.689 Hz. Directed reciprocal transfers are dependent, so track counts are not independent trial counts.

## Coverage and fallback

The frozen fit contains 1443 tracks. Of these, 104 fail the joint signal/candidate probability threshold and four lack training support, leaving 1335 eligible conditional cases. Same-candidate opposite-RX donors support 696; the remaining **639** retain zero-slope fallback. Across all 1335 eligible cases, median gain is therefore zero and mean gain is +10.184 Hz. Excluded and unsupported cases are retained explicitly, not counted as successful corrections.

Only 132 targets, from 23 scans, have both same- and other-candidate support. Comparisons against the other-candidate control use exactly this matched population. The target's own training slope improves 532/696 supported cases with median gain +16.521 Hz; this is a descriptive comparator, not independent calibration.

## Frozen method

The [protocol](PROTOCOL.md) reuses the [DS7–9 cross-RX method](../2026_09_29_candidate_rx_transfer/README.md) without changing its thresholds or scoring. All observations, geography, timings and training partitions come from the fixed DS10 N24_h0 baseline. Eligible tracks require training joint signal/MAP probability >=0.5 and at least five training points spanning five seconds.

Donors must be on the opposite RX in the same scan and exact RF. Training spans must overlap at least 50% of the target span, with at least five donor training points spanning five seconds inside it. Same-candidate prediction uses the existing median donor aggregation; the control first aggregates within each other candidate then across candidates. Target constants and time centers use only training observations. Held values never select donors or fit slopes.

Frozen bank catalogue indices establish candidate equality **only within a scan**. The reused helper calls this field `number`; here it is explicitly tagged `scan_local_catalogue_index`, not a NORAD number. No index is compared across scans. Assignments are model hypotheses rather than verified identities.

The baseline location and timings were trained using both receivers. Consequently this is conditional cross-RX residual transfer, not a wholly independent receiver holdout or calibration. Shared fitted-location error, timing error, orbit error, transmitter behavior, processing artifacts or incorrect associations can all contribute.

## Decision for the sub-km effort

The result argues against treating all residual drift as one receiver-wide correction: matching the candidate matters in this test. It supports the presence of candidate-specific shared structure in DS10 as well as DS7–9.

Do not add a free shared slope to the geographic model on this basis. The earlier [shared-candidate slope experiment](../2026_09_29_shared_candidate_slope/README.md) improved held prediction while often worsening location accuracy; such terms can absorb the position information being sought. The next useful step is a physical attribution test or an independent constraint that separates orbit/transmitter effects from location and timing sensitivity, with whole recording groups withheld. This result is evidence about residual structure, not yet a sub-km method.

## Verification

The three existing transfer tests pass, covering known-slope recovery and receiver/candidate separation, held-data mutation isolation, and RF/time exclusions. The runner verifies cached input/source hashes, scan order, and baseline training and held score replay to 1e−7. It completes in **15.48 seconds** within the 180-second cap. [results.json](results.json) preserves residual cases, exclusions, donors and all target errors; [summary.json](summary.json) includes scan and receiver breakdowns. The SHA-256 inventory binds all report artifacts.

No new RF, export, propagation, geographic fit, production edit or remote publication occurred.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_candidate_rx_transfer -p 'test_*.py'
cd reports/2026_09_30_ds10_rx_residual
sha256sum -c evidence.sha256
```
