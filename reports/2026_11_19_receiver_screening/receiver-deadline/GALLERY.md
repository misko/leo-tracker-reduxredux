# Receiver deadline gallery

[Browse the position and stage charts](index.html) · [Download the offline ZIP](modification-charts.zip) · [Verify exported files](pack-lock.json)

[Switch calibration in the position gallery](charts/index.html) · [Read the stage figures and data](stage-charts/README.md) · [See the complete chart inventory](chart-inventory.csv)

The gallery contains 15 position comparisons in both calibration settings and eight stage charts. The ZIP contains 38 standalone PNGs, the PDF books, the measurements, and file hashes. The 696 plotted position rows include repeated recordings across comparisons and separate diagnostic estimates where available.

Each position comparison uses the scheduled recordings or offers for that change in both calibration settings. The curves count withheld, failed, timed out, and unavailable attempts. A fitted diagnostic appears only when a run saved a numerical estimate. The roof comparisons show the original v5 options on the same recordings. The 5% and 10% allowances use original no-repair v5 on the same recording and calibration arm. RF residuals measure the frequency fit independently of geographic error. [Plotted position values](positions.csv) · [Position and RF summaries](summary.csv) · [Per-recording RF and position scores](position-rf.csv)

The stage charts cover detector parity, actual acquisition service, modeled dispatch, pilot support, and archived power-scan ranking. The external spectrum experiment uses one nominal RF center at an independent UK station. The fitted calibration coefficient cannot be isolated from a constant frequency offset at that boundary. [Study and receipt inventory](study-evidence.json) · [External spectrum method](external-spectrum/PROTOCOL.md)

## Rebuild the gallery and benchmark

```sh
evidence=reports/2026_11_19_receiver_screening/receiver-deadline
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark \
  --receiver receiver-deadline --out "$evidence"
.venv/bin/python -m tools.pipeline_eval.qualification.gallery_check "$evidence/charts" \
  --expected-charts 15
```

The command regenerates the charts, summary tables, and offline package from the sealed study inputs. Use the `--out` option to assemble a copy in another local directory. [Benchmark file hashes](benchmark-lock.json)
