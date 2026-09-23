# Full September 21 long-block input qualification

All 152 recordings in two metadata-frozen September 21 eight-hour blocks passed
the current position-input preparation check. The complete session-ID set was
written to `manifest.json` before any track or position outcome was opened:
72 scans beginning 2026-09-21 00:00 UTC and 80 beginning 08:00 UTC. Selection
used only `long_group_metadata/inventory.json`; it used no geography, position
outcome, prospective, test, or test113 source. Qualification itself reads the
track evidence required by the public position-input preparation port.

The later frozen long-cohort partition assigns the 00:00 UTC group to TRAIN and
the 08:00 UTC group to VAL; see
`../2026_09_23_long_inventory_complete/manifest.json`. This report does not fit,
select, or evaluate a position model, and does not make a sub-300 m claim. It is
an independent long-block input gate for such a future validation.

| UTC group | Frozen scans | Ready | Eligible >=3 s tracks | Eligible observations | Train / reserved observations |
|---|---:|---:|---:|---:|---:|
| 2026-09-21 00:00 | 72 | 72 | 3,587 | 97,993 | 57,335 / 40,658 |
| 2026-09-21 08:00 | 80 | 80 | 3,442 | 118,851 | 69,915 / 48,936 |
| **Total** | **152** | **152** | **7,029** | **216,844** | **127,250 / 89,594** |

Every selected ID is accounted for, and there were zero load or preparation
failures. Each scan loaded through the public read-only `ScannerTrackingInputStore`
and completed `prepare_adaptive_tle_position_inputs` against the read-only
`TleArchiveReader`. `results.json` retains per-scan input, analysis, raw-authority,
trajectory, evidence, and TLE snapshot digests; it also retains any load or
preparation error, so a rerun cannot silently omit a selected recording.

`results.json` binds the acquisition to
`qualify_full_acquisition_source.txt` with SHA-256
`6ae47d3154b34a9b3d428ae0cc56ef2bac020dc82bc79604789259924076e079`.
That artifact is an exact preserved copy of the helper used for the completed
qualification. The runnable `qualify_full.py` was subsequently changed only by
Ruff formatting and lint hygiene; its SHA-256 is
`3eb8b69d1d288b5df335572e0cc7e28ac7c04e5af0b8587c31ac6125d42ba1ad`.
The embedded `WORKER` program is byte-for-byte unchanged
(`52185f4f5367f0d18e8872f3d772f0484311480c543744f1ff88680c8d139c1f`).

The 00:00 block contains 21,604.615 s of summed capture support over a
28,740.862 s elapsed capture span; its maximum inter-capture-start gap is
1,152.600 s. The 08:00 block contains 24,005.446 s of support over a
28,739.901 s elapsed span; its maximum gap is 361.752 s. Those values describe
gappy capture support, not continuous eight-hour observations. Per-scan eligible
track-span statistics and first-sample timing fields are retained in `results.json`.

All 152 scans have qualified host-bracketed device-counter timing and a prepared
start equal to the saved timing authority. All 152 have a causal TLE snapshot with
10,695--11,114 candidate entries. These checks establish input availability and
causal catalogue coverage; they do not establish orbital association correctness
or location accuracy.

Reproduce from a fresh output directory in two phases so selection is visibly
frozen before position preparation:

```bash
.venv/bin/python reports/2026_09_23_long_block_full_qualification/qualify_full.py \
  --inventory reports/2026_09_23_long_group_metadata/inventory.json \
  --manifest /tmp/long-full-manifest.json --results /tmp/long-full-results.json --freeze

.venv/bin/python reports/2026_09_23_long_block_full_qualification/qualify_full.py \
  --inventory reports/2026_09_23_long_group_metadata/inventory.json \
  --manifest /tmp/long-full-manifest.json --results /tmp/long-full-results.json
```

The helper runs each bounded four-scan batch through the `leo` service identity
and public read-only adapters. No RF was collected or changed.
