# Interim DS1–DS3 scientific status

This is a sealed audit snapshot. It does not perform inference, satellite
association, position selection, or post-seal scoring.

The current package covers **DS3/all56** and has **30 terminal method arms out
of 49**. Nineteen arms remain pending, so publication readiness is **false**.
The pending set is recorded in
[`INTERIM_SCIENTIFIC_STATUS.json`](INTERIM_SCIENTIFIC_STATUS.json).

Two DS3 arms are currently labelled qualified by their source artifacts:
`fixed-hard-cone-orientation` and `local-fitted-full-fov-cone-position`.
These labels are provisional because neither arm currently has a qualified
DS1 comparator or an explicit cross-dataset accuracy gate. There are **zero** paired
DS1-versus-DS3 ranking-eligible comparisons: `qualified-only.csv` contains no
data rows. Nonqualified DS3 estimates remain in the all-estimates output as
diagnostics and are excluded from the qualified-only output and rankings.

The comparison references 38 DS3 artifacts. The audit found no true values in
their inference flags: `reference_coordinate_present`,
`reference_used_for_inference`, and `held_observations_used` are all false.
The Sausalito coordinate appears only in the sealed post-seal evaluation for
reporting errors after inference.

The package includes machine-readable comparison, post-seal, registry, and
audit JSON/CSV files alongside comparison, qualified-only, and all-estimate
PNGs. Historical DS1 coverage is incomplete: ten exact sealed multi-case
method evaluations are mapped, while 27 rows still lack an exact sealed DS1
selector or qualification record. See
[`DS1_COVERAGE_AUDIT.md`](DS1_COVERAGE_AUDIT.md).

This interim snapshot is publishable with its pending rows intact. The final
complete report remains blocked until every required DS3 arm is terminal, the
report is refreshed from sealed artifacts, and ranking eligibility is
reassessed.
