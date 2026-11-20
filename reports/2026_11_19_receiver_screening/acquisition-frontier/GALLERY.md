# Acquisition frontier gallery

[Browse the studies](index.html) · [Download the offline ZIP](modification-charts.zip) · [Verify the exported files](pack-lock.json)

The sealed release contains **49 charts**: 19 position comparisons in both calibration views and 11 measured stage charts. The position table contains 586 rows.

- The complete-recording FFTW comparison shows the two development recordings and two held recordings separately, then pools all four from one roof. [Pooling audit](diagnostic-whole/POOLED.md)
- The detector agreement chart covers 27,060 valid receiver probes across the two held recordings. [Stage chart](stage-charts/differential-capture-agreement.png)
- Both rescue-attribution comparisons use those two held recordings. Each shows one disjoint group of newly positive probes alongside the measured stock and union endpoints. [Rescue study](rescue-attribution/README.md)

Each position comparison shows the same scheduled recordings or offers under `c = 0` and fitted `c`. The position table retains the verdict for every scheduled attempt and leaves geographic error blank when an estimate or reference is unavailable. Stage pages link the observed quantities, units and denominators within each study’s measured boundary.

Rebuild this gallery from the sealed studies without replaying IQ or changing any other gallery.

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.receiver_core_pack \
  --evidence reports/2026_11_19_receiver_screening/acquisition-frontier
```

Unzip the offline bundle and open `index.html`. The bundle contains both calibration views, per-stage measurement CSVs, PDF books, and `artifact-sha256.json` for verification after extraction.
