# Screening figure evidence

Place a version 1 `figures.json` in the study directory beside its sealed predictions.
The same descriptor drives the standalone screening panel and the main position atlas.
Each export reads the evidence once for both calibration settings.
Independent subpanels can use nested directories and their own locks.

```json
{
  "version": 1,
  "charts": [{
    "id": "example",
    "method": "example",
    "scope": "roof",
    "title": "Example matched comparison",
    "caption": "Six recordings with the original tile and full archived detector factors.",
    "cases": "timing-six",
    "seal": "prediction-lock.json",
    "series": [
      {"key": "one", "label": "Candidate", "file": "positions.jsonl.gz", "value": "example"},
      {"key": "stock", "label": "Stock", "file": "stock-positions.jsonl.gz", "value": "orbit_projector",
       "match": ["input_sha256"]}
    ]
  }]
}
```

The seal declares the exact `cases` array and a `files` map from local basenames to
bare SHA-256 digests. Each series selects one row per case from an authenticated JSONL
or compressed JSONL file. A `field` override selects `variant` in place of the default
`method`. Use `where` for other exact row predicates such as an offer mode.
List additional sealed files in `provenance`. If the receipt stores a source hash
separately, `source_lock` names its `file` and the receipt's `digest_key`.

Roof charts take `roof135`, `timing-six`, `smoke-two` or an explicit fixed case list.
Each row binds its frozen native and causal catalogue hashes. An optional `native_field`
can point to the frozen capture authority when fresh detector bytes have a different hash.
Use `native_authority: "ordinary"` when an existing full ordinary-native receipt is
the relevant authority. Put only genuinely paired row keys in `match`.

Transfer charts use `scope: "transfer"`, `cases: "sealed"` and a `queries` filename
included in the same lock. Its `queries` array names each query's `id`, plotted
`condition`, physical or synthetic `recording` alias, committed `truth` coordinates
or null, and exact `bindings` to the prediction row. Positioning fixtures with
incompatible measurement contracts use `eligible: false`. Saved coordinates on such
queries can appear as diagnostics. Use `candidate` and `stock` for the two main series.
The transfer charts use the declared queries and their references.
Use the keys of `condition_labels` in the desired panel order when renaming conditions.

Predictions use the standard `result` envelope. Preserve every case including failures
and timeouts. For detector-only evidence, set `result.metrics.position_attempted` to false
and leave both positions and forced coordinates null.

```sh
.venv/bin/python -m tools.pipeline_eval figures --panel screening --arm both --out /tmp/screening
```
