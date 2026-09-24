# DS2 whole-corpus development manifest

This directory seals DS2 as the complete 20-capture, September 24 development
corpus after every frozen raw-eligible capture has an authoritative V14 tracking
product.  A session is included once and whole; DS2 deliberately does **not**
reuse the old train/validation/test split.  Any position comparison happens
only after a model has sealed its inference output.

The V14 products supply sealed tracklet and candidate-review evidence; they do
not supply satellite identity labels for blind positioning.  Every DS2 model
must recompute candidate predictions at each geographic cell and may not freeze
identities selected at a different location.

The positioning initialization is a fixed Sacramento administrative-centre
prior with a 250 km radius.  It is an input to inference, is explicitly marked
reference-free, and no receiver coordinate is present in the manifest or
receipt copies.

The manifest separates three compatible cohorts:

| Cohort | Sessions | Joint inference |
| --- | ---: | --- |
| `radio_pluto_19f2` / 15 MS/s | 1 | Single-session only |
| `radio_pluto_19f2` / 2.5 MS/s | 2 | Yes |
| `radio_pluto_5d4d` / 2.5 MS/s | 17 | Yes |

Only the three `.21` / `radio_pluto_19f2` captures with explicit
capture-time LT3D-001A bindings are eligible for geometry or fitted-cone
diagnostics.  RX0→negative-x and RX1→positive-x remain provisional, so those
models must marginalize the two RX-to-slot permutations.  The remaining 17
captures do not acquire geometry merely from their radio identity.

`build_manifest.py` refuses to write a final manifest while any of the twenty
authoritative tracking products remains incomplete.  It stores a compact,
content-addressed receipt for each completed product and records cache status
as `not_materialized` until an inference model creates a receipt-bound
prediction cache.  `manifest.sha256` and `tracking-receipts.sha256` bind the
manifest and the complete receipt index independently.

The first successful seal records `observed_utc`.  Later rebuilds preserve that
timestamp unless an explicit `--observed-utc` is supplied, so receipt rebinding
does not cause avoidable manifest churn.

Rebuild after tracking completes:

```bash
.venv/bin/python reports/2026_09_24_ds2_final_manifest/build_manifest.py
```
