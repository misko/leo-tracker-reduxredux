# Artifact scope and replay requirements

This directory preserves the review's new source, result tables, figures and
input hash bindings. No new position fit was run. It is not a complete raw-input
or runtime closure, and the publication does not change the operational model.

The `sources/` JSON files are exact copies from immutable commit
`dad19ba5ef74744d8234ccb4d461bac8444663aa`; `overview_metrics.json` binds their
original paths and SHA256 hashes. `methods/overview_audit.json` independently
checks all twelve means and the rounded README table. The small
`methods/evidence/` copies preserve prior local receipts and their provenance.

The identity and ACF JSON results can be inspected without the scan banks.
`identity/plot02.py` regenerates the current identity figure from the saved
`identity/evidence_summary.json`, using Python, NumPy and Matplotlib. The older
identity figure/report seal are explicitly superseded presentation provenance.
The current identity seal is `identity/report02_seal.json`; the ACF artifact
inventory is `acf/capsule_seal.json`. `publication_manifest.json` binds the
published files, excluding itself.

Scientific replay of `identity/review.py`, `identity/owner02.py` or `acf/audit.py`
also requires the exact original research paths recorded in their protocols,
inventories and seals. These include DS24 tracks/GLRT IDs, candidate ephemeris
and physical-mode banks, the parent radio/cavity results and complete accepted-ID
ledgers, and the earlier recovery, quadrature and transfer adapters. The sources
retain their original absolute paths and imports rather than silently changing
scientific context. They also need the matching repository modules and Python
NumPy/SciPy environment. The overview generator expects the original local
publisher path and uses `git show` on the immutable source commit.

Prior input releases and research snapshots are documented in the linked
[movement](https://github.com/misko/leo-tracker-reduxredux/blob/dad19ba5ef74744d8234ccb4d461bac8444663aa/reports/2026_10_25_ds24_movement_policy/README.md),
[uncertainty](https://github.com/misko/leo-tracker-reduxredux/blob/dad19ba5ef74744d8234ccb4d461bac8444663aa/reports/2026_10_25_ds24_new_family_uncertainty/README.md)
and [fast-identifiability](https://github.com/misko/leo-tracker-reduxredux/blob/dad19ba5ef74744d8234ccb4d461bac8444663aa/reports/2026_10_25_ds24_fast_identifiability/README.md)
reports. This review does not assert that those assets restore every external
input used here. A saved hash is an input identity check, not the corresponding
input bytes or proof of a clean scientific rerun. No independent clean full-input
replay was attempted for this compact review; only published-file, local-link and
recorded seal checks were performed. No IQ payloads or credentials are included.
