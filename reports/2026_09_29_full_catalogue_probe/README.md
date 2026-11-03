# Full-catalogue probe finds no local shortlist loss on nine sampled tracks

All nine sampled tracks retain their highest-scoring full-catalogue candidate
under both training and complete-track q020 contrast likelihoods. Retained
conditional signal mass rounds to 1.0 in every case. Fresh predictions for
retained candidates exactly reproduce the cached bank at the tested epochs.
This provides no evidence that local shortlist truncation explains these
sampled results, while leaving broader geographic coverage untested.

| Dataset | Tracks | Catalogue size | Valid propagated objects | Visible range | Retained visible range | Best retained |
|---|---:|---:|---:|---:|---:|---:|
| DS7 | 3 | 10,685 | 10,685 | 494–513 | 10–15 | 3/3 |
| DS8 | 3 | 11,130 | 11,129 | 538–571 | 13–19 | 3/3 |
| DS9 | 3 | 11,130 | 11,129 | 520–526 | 13–14 | 3/3 |

Mass 1.0 means unity to floating-point precision, not a mathematical proof
that omitted candidates have zero density. The probe evaluates only the
existing N24 location and timing offset zero. It does not test the full timing
prior, other locations, weak tracks, every track or the actual emitting identity.

## What the exporter actually conditions on

The current exported observations declare public projection with minimum
support/span and no geographic filtering. Candidate export is different:
`tools/ds7_export_baseline.py` evaluates five geographic anchors around the
fixed center (center and ±12 km east/north corners), 41 timing offsets, and
takes the union of the training-only top eight candidates at those settings.
The shortlist uses the exporter's robust offset-fitted likelihood; current
q020 experiments use normalized contrast likelihoods on the retained bank.

This pilot compares that retained membership with the current contrast
likelihood over the reconstructed full catalogue. It does not recompute the
original exporter's robust selection scores. The full-catalogue path is usable
as a bounded numerical oracle, so future coverage audits need not assume the
shortlist is complete. It does not yet provide an observer-independent global
localization search or remove the original site's influence on prior analyses.

## Frozen selection and exact reconstruction

Choose the earliest of the five frozen outside-pool targets in each dataset,
then the first three bank-eligible track IDs in sorted order. No posterior,
residual quality or reference error selected these tracks. The [manifest](manifest.json)
and [protocol](PROTOCOL.md) record this selection before execution.

The bank manifest supplies baseline and provider snapshot digests. The probe
reads them through the public read-only TleArchiveReader, applies the same
labelled-debris exclusion, reconstructs the exporter's newest-per-object
choice, and checks exact catalogue row identity. Propagation uses the original
rounded receive-time epochs at zero offset. The original training-mask horizon
rule is then applied. Invalid propagation is retained in the counts above;
every original shortlisted object was available for prediction replay.

For the retained-visible and full-visible candidate sets, the probe computes
training/full contrast likelihood sums and conditional retained mass. It also
compares q020 signal responsibilities using uniform priors over each visible
set. Full-catalogue signal probability remains effectively one here (minimum
training value 0.9999999999979252), but that is conditional on this signal and
background model and is not calibrated satellite-identification confidence.
Changing the visible-set normalization is a diagnostic, not a correction that
has been applied to the production or research fit results.

## Verification and implications

All three workers exited zero in 3.89–4.66 seconds under 120-second caps.
All nine retained-bank prediction replays had zero Hz discrepancy, and
visibility masks matched. Source artifact hashes, raw snapshot hashes, manifest
bindings, selected IDs and catalogue row counts were checked. Deployed oracle
module paths and hashes are retained in each output. The release interpreter
is used as a research numerical oracle, with no new production runtime dependency.
Ruff passed. No RF, QNAP mutation or archive modification occurred.

See the [full track table](TABLE.md), [summary](summary.json), and per-dataset
JSON for candidate numbers, responsibilities, timings and source provenance.

The next completeness check should broaden locations and timing offsets on
a fixed sample, especially before claiming any general search-region result.
This local nine-track result does not justify rebuilding every bank, nor does
it resolve the larger disagreement between predicted likelihood and reference
error. The inherited geographic reference remains exposed and unsurveyed.
No improved position or independently verified sub-km accuracy is claimed.

```bash
python3 reports/2026_09_29_full_catalogue_probe/study.py prepare
python3 reports/2026_09_29_full_catalogue_probe/study.py batch
python3 reports/2026_09_29_full_catalogue_probe/summarize.py
```

Batch execution uses the pinned deployed interpreter through read-only archive
operations. Outputs use exclusive creation; reproduce in a fresh archived-run
context. All report artifacts are local.
