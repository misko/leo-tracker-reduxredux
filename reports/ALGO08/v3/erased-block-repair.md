# Rebuilt forward forecasts on one erased future-only block

Rebuilding the forward fit after erasure made a paired held-Doppler comparison possible on **DS30-0057**. The update did not improve aggregate signed RF loss in either calibration arm. Six of the eleven held measurements missed their training-only predictions by at least **22.5 kHz**, and the largest miss supplied **73.4%** of the forward squared error in each arm. The fixed metadata labels and lifts provided too little reliable same-signal support to isolate the effect of the repair on calibration. **DS30-0016** retained just one usable held forecast and stopped before the paired refit. [Frozen protocol](erased-block-repair-protocol.md) · [Sealed forecasts and scored receipt](measurements/erased-block-repair.json.gz)

| Saved recording | Frozen held block | Factors erased | Rebuilt forward owners per arm | Future rows after guard | Qualified training additions | Matched held visits |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0016 | 10–20 s | 9 | 106 | 2 | Fit stopped before attachment | 1 |
| DS30-0057 | 50–60 s | 21 | 1,191 | 165 | 100 | 11 |

The block rule selected the earlier of the two middle occupied intervals. In the weak block, eight of the nine hidden measurements lacked a same-receiver, same-RF forward track within eight seconds. The remaining measurement had a visible predictive-track forecast in both arms, and one future training row had a possible attachment. The two-visit minimum therefore stopped the case. On DS30-0057, nine held measurements had ambiguous track choices and one lacked any existing same-lane track. The remaining eleven covered eleven visits, two satellites and three satellite/receiver groups within the single held interval. All eleven stayed above the horizon in both fits. The 100 training additions used only future-supported measurements outside the held interval and its two adjacent blocks. [Fold formation and fixed-label checks](erased_block_repair.py)

| DS30-0057 calibration | Forward held RMS (Hz) | Augmented held RMS (Hz) | Change in total squared error (Hz²) |
|---|---:|---:|---:|
| `c = 0` | 279,446.84 | 279,451.21 | +26,915,572 |
| Fitted `c` | 279,443.41 | 279,447.92 | +27,747,340 |

Absolute residuals decreased on seven of eleven rows in each arm. The largest error was about 794 kHz. All eleven rows contributed to the table in their original order. The original conditional Doppler gate's 450 Hz scale served only to describe these errors after scoring. The six large residuals could reflect a wrong owner or signed lift even where the metadata gave one visible track. The experiment supplies no external owner or alias labels to distinguish these possibilities. Training-only forecasts were sealed first, and both fits scored identical held rows, assignments and lifts against the subsequently read measured signed CFO. This evaluates conditional RF prediction for one metadata-enrolled interval. It leaves position accuracy, geographic decisions, and other time blocks unmeasured. [Per-row decisions and residuals](measurements/erased-block-repair.json.gz)

## Complete saved rebuild cost

| Recording | Archived forward / local repair reference CPU (s) | Erasure and continuation CPU (s) | Fresh forward rebuild CPU (s) | Forecast and repair CPU (s) | Complete saved process CPU / elapsed (s) |
|---|---:|---:|---:|---:|---:|
| DS30-0016 | 2.578 / 0.030 | 0.018 | 2.233 | 0.009 | 3.485 / 3.491 |
| DS30-0057 | 6.206 / 0.151 | 0.069 | 5.468 | 0.196 | 6.967 / 6.978 |

The fresh clocks include graph and noise preparation, both calibration fits and the ordinary forward exterior check. The DS30-0057 local training attachment used 0.152 CPU seconds within the forecast-and-repair stage. The complete subprocess clocks include startup, saved handoff, archive binding and sealing the forecasts. The archived forward references also charged publication grid work. No fresh grid, figure publication or raw receiver ran. The offline rebuild was necessary for this validation because the earlier fixed-forward audit found that deleting any occupied future-only block changed forward admission. It supplies no evidence that a second solve belongs in a realtime route. [Earlier forward dependence audit](crossfit-future-repair.md) · [Numerical and worker clocks](measurements/erased-block-repair.json.gz)

Run `erased_block_repair_trial.py run FRESH_DIRECTORY CASE` on `DS30-0016` and `DS30-0057`, then `erased_block_repair_trial.py score FRESH_DIRECTORY`. Use the release interpreter, frozen input packet and archive paths, shared one-core Gauss lock, CPU 2, nice 15, I/O priority 7 and one numerical thread. The first launcher stopped before fitting because the prior coverage digest had been transcribed incompletely. The corrected enrollment verified the unchanged coverage bytes and kept the frozen blocks. Thirteen focused and adjacent tests passed. The uncompressed scored receipt SHA-256 is `4a74459dad9351c2c34aa00a4b5d854806ed8dff6f0c0064459f9b843baff8db`. [Driver](erased_block_repair_trial.py) · [Tests](../../../tests/pipeline_eval/test_erased_block_repair.py)
