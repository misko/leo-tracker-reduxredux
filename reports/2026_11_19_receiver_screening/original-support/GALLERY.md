# Original detector support gallery

[Browse the studies](index.html) · [Download the offline ZIP](modification-charts.zip) · [Verify exported files](pack-lock.json)

The gallery contains 20 position comparisons in both calibration settings and 10 standalone stage charts. The [chart inventory](chart-inventory.csv) describes the measurement boundaries. The [position table](positions.csv) preserves all 1,931 plotted rows, including terminal outcomes and numerical diagnostics.

## Rebuild the gallery

```sh
evidence=reports/2026_11_19_receiver_screening/original-support
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.receiver_core_pack \
  --evidence "$evidence"
.venv/bin/python -m tools.pipeline_eval.qualification.gallery_check "$evidence/charts" \
  --expected-charts 20
```

Position figures retain each scheduled recording or offer in both calibration settings. They show withheld, failed, and unavailable cases in the denominator and display a numerical diagnostic only when an actual fit saved one. Roof comparisons use the four authenticated original-v5 options when available. The 5% and 10% position allowances compare published error with the original no-repair v5 error on the same recording and calibration setting. Frequency residuals characterize the support used by the fit.

The original detector kernel and lane screening pages measure detector work on saved signal windows. The fixed quarter waveform schedule directly measures detector factors from the selected windows before the compact fit. Its DS26-0162 position exceeds both original no-repair v5 allowances in both calibration settings. [Fixed waveform schedule](scheduled-waveform/PROTOCOL.md) · [Per-arm errors and RF](scheduled-waveform/scores.csv)

The prepared kernel processed the complete DS26-0237 recording. All 13,532 valid native probe rows matched the original capture, including all 60,306 candidates. Fresh fits from replayed and archived factors agreed in both calibration settings, with 0.353 km and 0.262 km errors and both paired v5 allowances met. [Complete replay audit](prepared-waveform/audit.json) · [Per-arm errors and RF](prepared-waveform/scores.csv)

Frequency scheduling fits stored factors from eight roof recordings, including six hash-selected recordings outside the earlier burst and dwell experiments. Continuous RF coverage and short bursts use equal calls within each of 15 clock bins. The timing model simulates ideal FIFO capacity from measured original-detector costs. Queue selection applies a separate one-waiting-window model to the original DS29-0082 arrival clock, then fits the observed factors it selects. All three one-worker model selections withheld in both calibration settings. The actual paced replay measures service timing, queue losses and emitted packets at the recorded clock. [Frequency schedule protocol](frequency-schedule/PROTOCOL.md) · [Modeled queue position results](queue-selection/scores.csv) · [Paced original replay](paced-original/PROTOCOL.md)

Rotating dwell uses the acquisition sample counters to change active RF channels while keeping each slot active for at least 30 or 60 seconds. Its mechanism cohort reuses the eight earlier frequency-schedule recordings. The two prospective recordings, DS26-0297 and DS29-0519, follow a predeclared hash order. Both schedules published both calibration settings on both prospective recordings. Two-lane rotation met neither paired v5 allowance on either recording. Four-lane rotation met both allowances on one of two recordings in each calibration setting. Position fits start at stored factors and the detector call counts are derived from the physical schedule. [Rotating dwell protocol](rotating-dwell/PROTOCOL.md) · [Per-arm comparisons](rotating-dwell/scores.csv)

On DS29-0082 the one-worker model admitted 507 FIFO and 497 RF-aware visits. The actual original-detector services emitted 387 FIFO and 370 RF-aware visits. Both compact fits withheld in both calibration settings. The actual paced fast-four FIFO emitted 4,836 visits and published both arms, with errors of 2.49 km and 2.34 km. Both exceed the paired original-v5 10% allowance. [Modeled admission ledger](queue-selection/forecasts.json.gz) · [Measured original and fast-four timing](paced-original/timing.csv) · [Measured RF-aware replay](paced-rf/README.md)

The outside-option test uses 48 newly drawn four-tile boards on prepared StarLoc traces from eight previously observed sites. Its earlier-held subgroup contains four physical sites and 24 new boards. Six of 16 containing queries published, while 2 of 16 near omissions and none of 16 wide omissions published. Both near false fixes occurred at earlier development sites. The geometry-only comparator publishes the offered center nearest the common Illinois anchor. Per-arc carrier offsets leave fitted calibration unavailable for this single nominal RF. [Enrolled site and offer geometry](outside-option/PROTOCOL.md) · [Outcomes by offer](outside-option/scores.csv)
