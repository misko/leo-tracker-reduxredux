# DS5 since local midnight

DS5 freezes every eligible adaptive recording whose first sample lies in the
fixed interval **2026-09-26 00:00:00–06:59:09 America/Los_Angeles**, equivalent
to **2026-09-26T07:00:00Z–13:59:09Z**. Both endpoints are inclusive. The upper
endpoint is the request-time cutoff, so the dataset cannot grow as later
recordings arrive.

Admission requires qualified UTC timing, a terminal `completed` receipt, and
finalization no later than the cutoff. These rules admit **42 of 42** discovered
recordings. The admitted capture starts span `07:00:02.360492Z` through
`13:50:02.667636Z`; all 42 use `radio_pluto_5d4d`. No reference location,
satellite identity, fitted parameter, or positioning result participates in
admission, grouping, or the inference manifests.

## Evaluation units

- **Single scans:** 42 units, one whole recording each.
- **Rate strata:** four ordered subsets: 14 at 2.5 MS/s, 10 at 5 MS/s, 9 at
  7.5 MS/s, and 9 at 10 MS/s. Each stratum includes ordered single-session IDs
  and a full rate-specific subset unit.
- **Active-dwell strata:** three truth-blind, rank-balanced subsets of 14 scans
  each, computed from the attested valid sample spans. Low spans 264.96–265.68
  active seconds, middle spans 265.68–265.92 seconds, and high spans
  265.92–266.64 seconds. Ties are resolved by session ID. The continuous
  active seconds, valid-duty fraction, and median visit dwell remain attached
  to every scan, so analyses need not depend only on the tercile labels.
- **Rate x active-dwell strata:** a machine-readable cross-tabulation preserves
  both factors for comparisons without conflating sample rate with usable
  exposure.
- **Groups of eight:** five chronological, non-overlapping, back-to-back units
  covering 40 recordings. Groups preserve chronology and are never rearranged
  by sample rate. Every group records its rate composition.
- **Remainder:** the last two recordings are declared explicitly and are not
  presented as an eight-scan unit.
- **Full dataset:** one unit containing all 42 admitted recordings.

Units record summed active seconds and the minimum, median, and maximum
per-session exposure. The full dataset contains 11,163.96 active seconds; its
median scan has 265.86 active seconds, 88.62% valid duty, and 120 ms median
visit dwell.

`manifest.json` binds each raw, read-only recording manifest by path and SHA-256
and preserves every admission decision. `evaluation-units.json` binds all unit
memberships to the admitted inventory digest. Every JSON authority has a
sidecar SHA-256 seal.

## Reproduction

The raw recording tree is read-only and requires the `leo` service account:

```bash
stage_dir=$(mktemp -d /tmp/ds5-freeze.XXXXXX)
chmod 777 "$stage_dir"
sudo -n -u leo .venv/bin/python \
  reports/2026_09_26_ds5_since_local_midnight/build_manifest.py \
  --output-dir "$stage_dir" \
  --manifest-logical-path \
  "$PWD/reports/2026_09_26_ds5_since_local_midnight/manifest.json"
```

The builder is deterministic for the sealed policy and immutable source
manifests. Validation covers inventory sealing, truth-blindness, whole-session
grouping, remainder handling, rate partitioning, and per-group rate
composition, plus active-time partitioning and the rate-by-active-time cross
strata.
