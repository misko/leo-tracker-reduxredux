# Scientific method registry contract

`method-registry.json` is the publication identity layer for the DS1/DS3
comparison. `method_id` is stable and unique per scientific arm. Integer
`iteration` remains optional provenance and is never used as method identity.

Each method records:

- a stable `method_id`, human-readable name, arm, and classification;
- its DS1 report source;
- an optional numbered-iteration provenance link;
- an explicit DS3 binding to a numbered result, sealed standalone artifact,
  terminal accounting disposition, or pending work; and
- explicit supersession where a later method invalidates or replaces an older
  one.

Every registry row is required for publication. Nonportable, missing-history,
and superseded methods satisfy the gate only through an explicit terminal
accounting status. A pending binding, missing seal, missing required arm label,
unexecuted DS3 diagnostic, nonterminal iteration result, or registry/ledger
digest mismatch keeps `publication_ready` false.

The registry is bound to the exact sealed 31-slot iteration ledger. Rebuild it
after the authoritative ledger changes:

```bash
.venv/bin/python \
  reports/2026_09_25_ds1_ds3_all_methods/build_method_registry.py
```

Generate the comparison and post-seal evaluation:

```bash
.venv/bin/python reports/2026_09_25_ds1_ds3_all_methods/run.py generate
.venv/bin/python reports/2026_09_25_ds1_ds3_all_methods/run.py postseal \
  --reference-latitude 37.84903264307456 \
  --reference-longitude -122.4856541910174
.venv/bin/python reports/2026_09_25_ds1_ds3_all_methods/run.py generate \
  --postseal reports/2026_09_25_ds1_ds3_all_methods/postseal-evaluation.json
```

The reference coordinate enters only the post-seal evaluator. It is never
available to inference or method selection.
