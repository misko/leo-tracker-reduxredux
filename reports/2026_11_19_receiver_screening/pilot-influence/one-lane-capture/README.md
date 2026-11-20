# One original-capture antenna per valid visit

This experiment separates detector source from the two-to-one antenna change on six previously difficult recordings and two fixed controls. Each of the four cells uses the installed compact phase-release solver with the original tile, causal TLE catalogue, configuration, three initial branches, and both calibration arms. The original v5 policies appear separately as frozen archival references.

| Detector source | Both antennas | One antenna |
| --- | --- | --- |
| Original capture-era GLRT | Fresh fit of exact authenticated historical native bytes | Fresh fit with alternate receiver candidate arrays emptied |
| Fixed four timing regions | Authenticated earlier complete saved-IQ run | Independent fresh fit of the fixed-four packet projected on the identical physical schedule |

The scheduler uses the integer center from each authenticated raw segment target manifest. Per center it starts with RX0, advances only on valid visits and selects one receiver even when its candidate array has no gated winner. Both receiver envelopes remain, including clocks, RF and sample counters, and all original invalid/excluded visits remain unchanged. The [schedule audit](schedule-audit.jsonl.gz) contains every selected visit and separately records how many original winners fixed four missed on selected and omitted lanes using the same epoch and absolute CFO rule as [the earlier pilot qualification](../../receiver-choice/hard-pilots/README.md).

Across 52,126 valid visits the alternating schedule retained 17,277 of the 34,413 original gated winners (50.2%). Fixed four produced 17,736 gated probes on the chosen lanes, yet 1,453 of the retained original winners had no matching gated fixed-four candidate within two samples and 1 kHz of absolute CFO. The positive count and agreement on specific measurements describe different aspects of support.

The fresh original-capture fits ran on two pinned lanes under a physical 512 MiB, zero-swap cap. Their clocks cover stored native factors through position. The antenna masks use already-recorded factors. The evidence concerns estimator sensitivity to observed support and provides no detector runtime measurement for single-lane original acquisition. This panel uses eight recordings from the same roof, including six previously difficult cases.

## Results

All four input variants produced fixes within 5 km on all eight recordings in both calibration arms. Masking one lane of original capture-era data increased the error on each of the six difficult recordings and decreased it on both controls, in both arms. For DS26-0122 the fitted-c error rose from 0.745 to 2.746 km. For DS29-0082 it rose from 0.516 to 2.033 km even as conditional RF RMS fell from 96.68 to 77.80 Hz.

| Compact input | c = 0 median / P95 (km) | Fitted c median / P95 (km) | Conditional RF RMS medians, c = 0 / fitted (Hz) |
| --- | ---: | ---: | ---: |
| Capture-era, both RX | 0.541 / 2.470 | 0.597 / 2.473 | 76.41 / 76.44 |
| Capture-era, one RX | 1.041 / 2.434 | 0.954 / 2.496 | 82.01 / 82.00 |
| Fixed four, both RX | 0.737 / 2.080 | 0.814 / 1.986 | 83.98 / 83.92 |
| Fixed four, one RX | 0.871 / 1.786 | 0.890 / 1.733 | 90.89 / 90.84 |

Capture-era one-lane inputs shortened the stored-factor solve on all eight pairs. The median paired reductions were 36.6% CPU and 36.5% wall. Across the eight pairs, the maximum observed physical memory peak was 450.1 MiB with both RX and 392.9 MiB with one RX. The fixed-four results were measured in their own studies and do not enter these resource comparisons.

## Evidence and reproduction

- [Position charts and calibration books](charts/index.html)
- [Both-arm per-recording scores](scores.csv), [matched changes](effects.csv), and [coverage and error distributions](summary.json)
- [Physical pilot support](pilot-support.csv) and [four original v5 roles](original-v5.csv)
- [Prospective plan](plan.json), [prediction lock](prediction-lock.json), and [fixed-four source receipts](comparison-sources.json)

From the repository root, use the following to verify the frozen rows and regenerate the reports and plots. `--work` optionally takes the original local scratch path to verify the staged packets and service logs as well.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.one_lane_capture_results
```
