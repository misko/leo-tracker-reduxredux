# Four and five timing regions from complete I/Q through position

This benchmark follows twenty distinct recordings from the same surveyed roof. Twelve had already run through the stock four-region detector. Eight had also formed a separate four-versus-five comparison, with two stock results in common. The ten earlier stock-only recordings now run the five-region receiver, and two more recordings were selected by acquisition-manifest identity before their scores were known. [Frozen schedule](roster.json) · [Comparison and inclusion rules](PROTOCOL.md)

The raw receivers estimate pilot timing and Doppler from the saved I/Q. The same compact phase-release solver turns their emitted observations into a position using the capture-era region and causal orbital catalogue. Each of the four original v5 comparisons uses the original archived detector measurements from its corresponding capture. Geographic error is the distance to the surveyed roof. A lower conditional RF residual describes the observations fitted by that receiver. [Earlier stock-only executions](../../track-recovery/wide-roster/README.md) · [Original eight comparisons](../../arrival-and-timing/fresh-replay/README.md)

## Twenty matched recordings

| Receiver | Fixes | Median km, zero / fitted | P95 km, zero / fitted | Within 5% of v5, zero / fitted | Within 10% of v5, zero / fitted |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original v5, no repair | 20/20 | 0.739 / 0.724 | 1.719 / 1.653 | 20 / 20 | 20 / 20 |
| Original v5, selective gap | 20/20 | 0.739 / 0.724 | 1.719 / 1.653 | 20 / 20 | 20 / 20 |
| Original v5, one omitted | 20/20 | 0.703 / 0.695 | 1.719 / 1.653 | 20 / 20 | 20 / 20 |
| Original v5, two omitted | 20/20 | 0.703 / 0.695 | 1.719 / 1.653 | 20 / 20 | 20 / 20 |
| Four timing regions | 20/20 | 0.774 / 0.776 | 1.592 / 1.388 | 10 / 11 | 11 / 11 |
| Five timing regions | 20/20 | 0.746 / 0.824 | 1.567 / 1.533 | 12 / 11 | 12 / 12 |

Every comparison uses all twenty recordings as its denominator. With fitted calibration the four-region median was 7.1% above original v5, and the five-region median was 13.8% above it. Both fast methods improved the full-panel P95. Five regions gave a smaller fitted error than four on 12 recordings, with a median paired change of −14 m. The largest improvement was 997 m and the largest increase was 1,120 m. The difference between the two medians and the median of paired recording differences summarize different quantities. [Fitted distribution](charts/fitted_c/complete-detector-roster-all.png) · [Zero-calibration distribution](charts/c0/complete-detector-roster-all.png) · [Individual recording differences](paired-errors.csv)

On the ten newly filled comparisons, each method met the 10% fitted allowance on 5/10. Their fitted median errors were 0.781 and 0.828 km for four and five regions. The two entirely new recordings each favored a different detector by about a kilometre. Replacing stock with its first eligible launch on the original twelve changes coverage on the complete roster from 20/20 to 19/20. The missing DS29-0082 position stays in the denominator. [Previously stock-only recordings](charts/fitted_c/complete-detector-roster-ten.png) · [First-attempt sensitivity](charts/fitted_c/complete-detector-roster-first.png) · [All thresholds and percentiles](summary.csv) · [Geographic and RF values for each arm](scores.csv)

## Time from saved samples to position

The median time through both position fits was 176.74 s with four timing regions and 214.19 s with five. Of 132,740 complete two-antenna detector calls per policy, 55.62% and 21.32% finished within 20 ms. Six recording pairs used the same pinned cores for both methods. Four regions finished sooner on every one of those pairs, and 91.54% of their detector calls finished within 20 ms versus 52.52% with five. The other fourteen pairs ran on different core assignments. These offline host timings measure elapsed computation. The arrival-paced trials separately measure time spent waiting in the receiver queue. [Runtime by recording](runtime.csv) · [First-attempt timing](runtime-first-attempt.csv) · [Clock boundaries and service receipts](../complete-timing/README.md) · [Arrival-paced trial](../combined-native/README.md)

## Rebuild

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark --out /tmp/complete-detector-roster
```

The output includes the cumulative comparison, the ten recordings that previously lacked a fifth-region result, and the earlier-stock-attempt sensitivity. For the latter, the twelve recordings with an archived attempt ledger use their first eligible stock attempt. The other eight retain the same stock run. A timed-out recording stays in the denominator and has no geographic value. The command also verifies that the native detector and scientific position records match the timing receipts for every run, then exports the per-run timing tables and their [machine-readable summary](runtime-summary.json).
