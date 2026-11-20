# Latency and support gallery

[Browse the studies](index.html) · [Download the offline ZIP](modification-charts.zip) · [Verify exported files](pack-lock.json)

The gallery contains 20 position comparisons in two calibration settings and eight standalone stage charts. Each plot and its table appear in the [chart inventory](chart-inventory.csv). The 40 position views contain 1,129 recorded comparison rows in [positions.csv](positions.csv). The AArch64 stage reports Cortex-A53 QEMU measurements, with physical board timing unmeasured. [ARM detector report](arm-receiver/README.md)

## Rebuild the gallery

```sh
evidence=reports/2026_11_19_receiver_screening/latency-and-support
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.receiver_core_pack \
  --evidence "$evidence"
.venv/bin/python -m tools.pipeline_eval.qualification.gallery_check "$evidence/charts"
```

To render one comparison in both arms, select its chart ID with the normal CLI.

```sh
out=$(mktemp -d)
.venv/bin/python -m tools.pipeline_eval figures --panel screening --evidence "$evidence" \
  --variant new-waveforms-all --arm both --out "$out"
```

The gallery keeps every scheduled recording or offered query in both calibration settings. Withheld, failed, timed-out, and missing attempts retain their status. Geographic error is blank when the run issued no estimate. Standalone detector or timing charts use their own measurement denominators.

New position studies use `"version": 2` at the top of `figures.json`. This displays the scheduled denominator even when every position fails or times out. It preserves the reported terminal status when a receiver exits before refinement. The version 1 figures still rebuild using their published display. Standalone `stage-figure.json` descriptors use version 1.

The measured ORBCOMM comparison uses a fixed zero calibration. The fitted arm is unavailable because the per-pass offsets span the RF calibration term. The chart export retains that source reason and the full offered-query denominator with empty fitted coordinates. [ORBCOMM figure receipt](external-position/figure-lock.json)

The complete four-region versus fifth-region comparison combines the original 18 recordings with two metadata-selected recordings from the same roof. Both primary detector paths returned positions on all 20 recordings in both calibration arms. A separate first-attempt view retains the earlier stock timeout on DS29-0082 and shows 19/20 stock fixes. The fresh DS29 recordings use all four authenticated capture-era v5 references. [Complete comparison](complete-roster/README.md) · [Scheduled recording IDs](complete-roster/roster.json)

## Arrival and service clocks

The archived paced-replay case rows use recorded physical arrivals and observed native packet emissions. They count actual dropped valid arrivals and separate the hardware-invalid ones. The archived FIFO model estimates completion and drops from saved native CPU or wall intervals at a stated worker count and waiting capacity. The buffered experiment labels the historical one-slot and new four-slot measurements independently from the fixed-service model. [Observed replay rows](../support-preserving/arrival-queue/paced-replay.csv) · [Archived model rows](../support-preserving/arrival-queue/queue-model.csv) · [Observed buffer rows](../arrival-and-timing/buffered-replay/buffered-stage.csv) · [Buffer model rows](../arrival-and-timing/buffered-replay/fixed-service-model.csv)

On DS29-0316, fifth-center dropped 55 valid visits in the actual one-slot replay. The one-slot model predicts 0 drops using the archived CPU intervals and 113 using archived wall intervals. The measured result and both projections remain separate case rows. [Actual drop ledger](../support-preserving/arrival-queue/observed-drops.csv) · [Modeled drop ledger](../support-preserving/arrival-queue/modeled-drops.json.gz)

Window duration, native detector time, schedule-to-emission age, and post-acquisition position-fit time use separate clocks. The scaled service study's 42 queue rows are modeled. Its fitted positions come from separate measured runs on those selected packet sets. [Scale-study rows](../arrival-and-timing/queue-capacity/queue-model.csv) · [Fit and RF rows](../arrival-and-timing/queue-capacity/position-scores.csv)
