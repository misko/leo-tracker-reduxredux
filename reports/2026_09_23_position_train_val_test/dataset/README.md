# Position recording dataset split

This manifest provides a fixed recording-level split for model development toward
sub-300-metre positioning over several duration scales. It does not manufacture an
untouched test set from recordings whose outcomes have already been examined.

| Partition | Recordings | Status |
|---|---:|---|
| Training | 64 | Original 16 plus the first 48 exposed day recordings |
| Development validation | 49 | Retrospective exposed recordings after a 120-minute embargo |
| Train/validation embargo | 19 | Excluded from both partitions |
| Validation/test embargo | 2 | Metadata only; excluded from prospective test |
| Prospective test | 0 | Unavailable at this snapshot |

The training cohort ends nominally at 04:25:01 UTC. Development validation begins at
06:30:30 UTC and ends nominally at 14:35:28 UTC. The 120-minute embargo is a
conservative boundary; it does not establish independence or prevent the same
satellite recurring. The effective prospective-test boundary is therefore 16:35:28
UTC, later than the original 15:15 exposure cutoff.

Three post-publication candidates existed in the metadata snapshot. One was captured
at 15:10, before the exposure cutoff, and two were captured at 15:20 and 15:30 inside
the validation/test embargo. Position diagnostics and eligibility were not opened for
them. Consequently, there is no untouched test recording in this manifest.

The prospective rule reserves the first normally acquired eligible recordings at or
after 16:35:28 UTC. Forty-eight eligible recordings are only a readiness milestone.
The preliminary test remains sealed until at least 144 eligible IDs can provide three
nonoverlapping 48-scan windows. This rule does not authorize or wait for new RF
collection.

Both available partitions expose fixed, nonoverlapping windows within each duration
tier: one scan, 6 scans, 18 scans and 48 scans. These correspond approximately to a
single 300-second capture, one hour, three hours and eight hours at the observed
cadence. Every window reports summed API-declared nominal capture duration separately
from elapsed first-start to nominal last-end span. Windows from different tiers reuse
recordings and are therefore views of the same partition, not independent folds.

Every window carries an authority digest over its sessions' published track evidence,
which binds observation IDs and the existing randomized within-track masks. Consumers
must retain those masks. `load_partition()` in
`tools/research/position_dataset_split.py` verifies the manifest content digest,
partition disjointness, embargoes, and duration-window isolation before returning IDs.

Reproduce the frozen manifest from the repository root with:

```bash
sudo -n -u mouse9911 -g leo .venv/bin/python \
  tools/research/position_dataset_split.py \
  --original-selection reports/2026_09_23_sixteen_scan_position_resolution/selection.json \
  --original-scans reports/2026_09_23_sixteen_scan_position_resolution/scans.json \
  --original-evidence-audit reports/2026_09_23_sixteen_scan_comparison/evidence_audit.json \
  --day-inventory reports/2026_09_23_day_position_validation/inventory.json \
  --output <fresh-output-directory>
```
