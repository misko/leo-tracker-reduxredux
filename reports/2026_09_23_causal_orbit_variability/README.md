# Causal catalogue-update variability: first long TRAIN scan

This bounded TRAIN-only audit compares the saved causal TLE snapshot for
`scan-hop-85afa91453f8847b` with its immediately preceding archive snapshot.
It is an update-to-update inconsistency proxy, not a calibrated orbital-error
distribution and not a position result. No receiver truth, RF outcome, orbital
association, or position fit was used.

The scan begins at `1789948815631878033` ns. Both snapshots were selected with
the public `TleArchiveReader.select_latest_before` API under the same strict
cutoff, start minus 505 seconds. The saved causal snapshot
`515b0921…d8360c8e` was collected 2,928.813 seconds before that cutoff; its
immediate predecessor `6c4ee22c…f763df03` was collected 6,670.578 seconds
before it. The receipt records the full hashes, timestamps, ages, and the strict
causality invariant.

All 880 regional NORAD IDs from the frozen first-16 TRAIN cache were present,
propagated, and matched in both 11,114-object snapshots. All 880 had identical
element-pair digests across this particular snapshot pair. Consequently, at the
representative beginning, middle, and end TRAIN epochs (2.555, 192.503, and
299.992 seconds after capture start), the current-minus-preceding relative
position is exactly 0.0 m in radial, along-track, and cross-track components.
After removing a separate constant CFO from each NORAD's three-point Doppler
difference, Sacramento and Reno shape differences are also exactly 0.0 Hz.

That zero is evidence only that these two snapshots contain the same elements
for this cached regional inventory. It neither bounds catalogue-update
variability at other update boundaries nor shows that 0.02 Hz interpolation is
dominant. Catalogue update age alone is not an uncertainty calibration; this
audit supplies a concrete local inconsistency check motivated by the possibility
of material orbit error, which must be assessed from this archive's data rather
than inferred from a general literature warning.

## Bounded earlier causal history

`history_results.json` preserves the immediate-pair zero and walks backward
from that baseline through adjacent archive pairs only. Its hard limits are 24
predecessors and 24 hours before the baseline; it never reads a later snapshot.
The first two adjacent pairs were also unchanged for all 880 regional NORADs.
The third pair was the nearest changed boundary: newer snapshot
`6004eb4c…deca7872`, 13,847.540 s old at the causal cutoff, versus older
`d65bd1bc…3ea2d24`, 20,895.556 s old. It changed 858 regional element pairs;
22 of the 880 cached IDs were absent from the older snapshot, so all-
inventory accounting must retain that missing set.

For the 858 NORADs propagated in both sides of that changed pair, the absolute
RTN current-minus-prior medians were 57.327 m radial, 2,693.805 m along-track,
and 95.608 m cross-track. P99 values were 3,389.240 m, 176,595.323 m, and
5,787.287 m respectively. With a per-NORAD constant CFO removed, median
three-epoch Doppler-shape RMS was 58.777 Hz at the Sacramento centre and
58.624 Hz at Reno; P99 was 12,494.988 Hz and 10,728.712 Hz. Because every
propagated common NORAD in this pair had a changed element set, the changed-
subset and common-all-candidate summaries coincide; the report still writes
both so an unchanged majority could not hide a changed subset in another pair.

These are changes between two causal catalogue solutions at the scan's training
epochs, not errors against an orbit truth. They show that the immediately prior
refresh was uninformative while an earlier, still-causal update boundary is not;
they do not calibrate an orbital nuisance prior or prove a location error.

`results.json` records candidate/missing/propagation/identical-element
accounting, ECEF RTN component quantiles, the constant-CFO-removed Doppler-shape
quantiles at the Sacramento and Reno centres, timing and snapshot provenance,
and source hashes. `audit.py` is the reproducible, lint-clean helper; its output
binding is `sha256:a08b094f4b09f28c82464f95b17f05a60e054705d1dcfaa9eeedda18c2f032db`.
`history.py` is the separate lint-clean bounded-history helper, bound by
`history_results.json` as
`sha256:e9f2db32fee201150b66fb91413fa90e87a067295a9cc2c9f518699fe8e9b377`.

Reproduce through the read-only service identity:

```bash
sudo -n -u leo .venv/bin/python reports/2026_09_23_causal_orbit_variability/audit.py \
  --session-id scan-hop-85afa91453f8847b \
  --cohort-manifest reports/2026_09_23_long_inventory_complete/manifest.json \
  --cache-receipt /tmp/leo-long-training-cache-first16/scan-hop-85afa91453f8847b/cache_receipt.json \
  --output /tmp/causal-orbit-variability.json
```
