# Support-preserving receiver gallery

[Browse the studies](index.html) · [Download the offline ZIP](modification-charts.zip) · [Verify the exported files](pack-lock.json)

The archive’s **81 charts** cover 34 position comparisons in both calibration settings and 13 measured receiver stages. Its position table contains 1,166 rows.

The arrival-queue study includes four complete detector runs paced at the recorded delivery cadence for DS26-0197 and DS29-0316. The two position comparisons use the packets that actually emitted after queue drops. [Paced measurements](stage-charts/paced-native-arrival-queue.csv) · [Stock position](charts/index.html#screening-paced-position-control) · [Fifth-center position](charts/index.html#screening-paced-position-candidate)

The gallery reads sealed study results. Position comparisons keep the same scheduled recordings and offers in both calibration views. Stage pages show the quantities measured at their own receiver boundary.

## Build the offline gallery

```sh
evidence=reports/2026_11_19_receiver_screening/support-preserving
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.receiver_core_pack \
  --evidence "$evidence"
```

Open the generated `index.html` or extract `modification-charts.zip` and open its copy of the index. The archive’s `artifact-sha256.json` lists the checksums of the extracted files.

## Select one comparison

When the position gallery contains several comparisons, use **Find a modification** in `charts/index.html` to search by title or ID. The two calibration buttons switch the view for the same comparison. An exact ID also opens `charts/index.html#screening-<id>`. The stage manifest at `stage-charts/manifest.json` lists the IDs for direct `index.html#<id>` links.

To render just one position comparison outside the complete gallery, list the available IDs and set `chart_id` to the one you want. This example selects the first listed comparison.

```sh
evidence=reports/2026_11_19_receiver_screening/support-preserving
jq -r '[.[].id] | unique[]' "$evidence/charts/manifest.json"
chart_id=$(jq -er '.[0].id' "$evidence/charts/manifest.json")
out=$(mktemp -d /var/tmp/leo-support-chart.XXXXXX)
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval figures --panel screening \
  --evidence "$evidence" --variant "$chart_id" --arm both --out "$out"
printf 'Open %s/index.html\n' "$out"
```

`--variant` matches chart IDs and method IDs. A name shared by several cards returns every match. A gallery’s `#screening-<id>` link opens the exact card.
