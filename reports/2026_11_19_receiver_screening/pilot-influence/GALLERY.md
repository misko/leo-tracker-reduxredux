# Pilot influence gallery

[Browse the studies](index.html) · [Download the offline ZIP](modification-charts.zip) · [Verify exported files](pack-lock.json)

The gallery includes 31 position comparisons in two calibration settings and 11 standalone stage charts. The [chart inventory](chart-inventory.csv) lists each plot and its measured boundary. The [position table](positions.csv) retains 2,608 plotted rows for the recordings and offers.

## Rebuild the gallery

```sh
evidence=reports/2026_11_19_receiver_screening/pilot-influence
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.receiver_core_pack \
  --evidence "$evidence"
.venv/bin/python -m tools.pipeline_eval.qualification.gallery_check "$evidence/charts"
```

Position comparisons keep the scheduled recording or offer roster in both calibration settings. Withheld, failed, and unavailable outcomes retain their disposition. A numerical diagnostic estimate appears separately when the receiver saved one. The calibration arms use the same inputs and search budget within each comparison. Frequency residuals describe the support each receiver fit, so the geographic score and conditional RF score are separate measurements.

## Compare the measurement boundaries

A single-lane projection retains the original physical receiver identities, capture clocks, RF centers, and validity flags and empties the unused probe candidates. It measures the position solver on stored factors. The alternating policy uses both physical antennas over a recording, with one selected on each valid visit independently at each RF center. A direct replay processes the selected lane of the original saved samples before fitting position. The position comparison uses exact selected-lane parity against the corresponding detector output when available. Earlier capture-era and ordinary-native one-lane projections showed different geographic outcomes on the same recordings. [Prior single-input study](../../2026_11_19_receiver_frontend/single/README.md)

The direct one-lane streams on DS26-0014 and DS29-0082 match their stored-factor projections byte for byte and reproduce the position and RF results. The benchmark has complete one-lane acquisition clocks for those two recordings. The other 20 one-lane inputs have measured position fits and blank acquisition times. [Physical replay parity](one-lane-whole/parity.json) · [Accuracy and timing rows](one-lane-benchmark/accuracy-and-time.csv)

The second-on-miss replay uses the same alternating primary antenna and runs its partner only if the primary has no strict fractional-gate candidate. The two actual saved-IQ runs have per-visit clocks and byte-matched reconstructed factors. Stored-factor position fits have no acquisition clock. [Actual partner-call and parity evidence](second-on-miss-whole/parity.json) · [Measured detector calls](second-on-miss-whole/timing.csv)

The predecoded pace trial measures two detector policies in BA and AB order on the same saved recording and delivery clock. The service ledger separates emitted packets, queue drops, and hardware-invalid arrivals. The location comparisons fit the packets each actual replay emitted. [Measured pace table](paced-controlled/timing.csv) · [Paired position views](paced-controlled/figures.json)

Roof views use the authenticated original four capture-era v5 policies. An intervention that supplies known archive winners is a diagnostic on those inputs. Offered-region studies distinguish an omitted tile from an unavailable fit and retain any publication on an omission in the reported outcome. Stage charts identify their measured detector, factor, or host timing boundaries.

The winner-transplant availability comparison retains DS29-0357 as unavailable under its original launch horizon. The later same-input run has its own comparison. [Primary chart evidence](winner-transplant/figures.json) · [Separate make-up](winner-transplant/makeup/availability/figures.json)

The clock-geometry charts use six offers over three observation archives. Their clock-prior and original-clock receivers retain their zero-calibration results. Fitted calibration is unavailable for both because the per-arc levels absorb fixed RF calibration. [Matched clock comparison](clock-geometry/figures.json)

The StarLoc comparison uses 32 newly arranged boards at eight measured locations. Four locations informed an earlier development study. Each set holds three decoy tiles fixed while changing the fourth tile. Their symmetric placement supplies a geographic prior. The frozen receiver ranks tile fits from RF evidence. The omitted conditions place the true site approximately 1 km beyond a face, 1 km beyond both corner axes, or 20 km beyond a face. Fitted calibration is unavailable at the nominal beacon RF after the per-arc level is fitted. [Board construction and evaluation](independent-site/PROTOCOL.md) · [Per-offer scores](independent-site/scores.csv)
