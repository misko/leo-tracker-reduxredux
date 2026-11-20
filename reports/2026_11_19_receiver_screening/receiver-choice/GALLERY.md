# Receiver choice gallery

[Browse the studies](index.html) · [Download the offline ZIP](modification-charts.zip) · [Verify exported files](pack-lock.json)

The gallery includes 16 position comparisons in two calibration settings and eight standalone stage charts. The [chart inventory](chart-inventory.csv) lists each plot and its measurement boundary. The [position table](positions.csv) contains 1,484 rows and retains every plotted recording and offer. Rebuilding from the sealed study files reproduced the archive byte for byte.

## Rebuild the gallery

```sh
evidence=reports/2026_11_19_receiver_screening/receiver-choice
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.receiver_core_pack \
  --evidence "$evidence"
.venv/bin/python -m tools.pipeline_eval.qualification.gallery_check "$evidence/charts"
```

Position descriptors use version 2 and keep the same scheduled recordings or offers in both calibration settings. Failed and unavailable runs remain in the denominator with blank position values. A receiver can withhold before refinement or report a separate diagnostic estimate after a fit. The gallery identifies each outcome by its recorded status.

Roof charts use all four original v5 policies on the authenticated capture-era inputs. For these studies, DS26-0144 has an existing frozen reference. DS29-0491 uses its own capture-era authority and sealed original v5 reruns. Both are additional whole-IQ recordings for the detector comparison at the existing roof.

Native detector measurements, measured positions from retrospectively mixed packets, and modeled wall or queue costs have distinct boundaries. Missing-region comparisons use the exact supplied offers and separately identify any position issued on an omitted offer.

The staggered benchmark includes 20 positions fitted from reconstructed stock and fifth-center antenna packets and two positions from direct saved-IQ staggered detection. The two input sources have separate views in addition to the pooled comparison. The reconstructed fits measure position from the mixed packet set. Their detector runtime is unavailable. [Staggered benchmark](staggered-benchmark/README.md) · [Direct saved-IQ trials](staggered-whole/README.md)

The prefix comparison reports 20 retrospective choices among complete archived detector outputs and three new compact fits on composed factor arrays. Its measured boundary starts after acquisition. The equal-pace comparison instead runs both detectors on the same saved waveform and recorded arrival clock, then fits the packets each replay actually emitted. [Prefix policy](prefix-evidence/README.md) · [Equal-pace replay](equal-pace/README.md)
