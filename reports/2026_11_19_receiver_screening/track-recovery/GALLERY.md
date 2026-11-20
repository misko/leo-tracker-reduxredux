# Track recovery gallery

[Browse the studies](index.html) · [Download the offline ZIP](modification-charts.zip) · [Verify exported files](pack-lock.json)

Position pages show both RF calibration arms on the same scheduled recordings or offers. Failed, withheld and timed-out position attempts stay in the CSV. A stage that ended before position fitting contributes its measured stage chart and CSV.

Rebuild the scoped gallery from the sealed evidence without replaying radio samples.

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.receiver_core_pack \
  --evidence reports/2026_11_19_receiver_screening/track-recovery
```

Each measured stage can opt in with a `stage-figure.json` alongside its source files. It names the chart `id`, `title`, measured `sample`, input and output `boundary`, a `note`, and local `seal`, `image` and `csv` basenames. Set `version` to `1`. A `pdf` basename also preserves an original standalone PDF. A stage enters the gallery once the seal’s `files` map binds the PNG, CSV and any standalone PDF by SHA-256. The standard `figures.json` contract supplies attempted position comparisons.
