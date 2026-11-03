# Curvature seed-selection audit v1

This is a read-only audit of the frozen `server-a250` run. It replays only the
seed enumeration and ordering in `curvature_tracks.cpp`; it does not rerun the
tracker, detector, or raw IQ. The reconstructed counters exactly match the
frozen stderr: 8 lanes, 3,380 source groups, 26,237 seed pairs considered, and
4,096 retained (512 in every lane). There were 19,014 valid seeds before the
per-lane caps.

For diagnosis after the run, a seed is compatible with a maintained reference
segment when both endpoints use source groups in that segment and each CFO is
within the frozen 2,500 Hz circular comparison gate. All 36 one-to-one complete
segments had a compatible retained seed. Nine of the 10 segments represented
completely only through a merge had one. All 17 segments without any complete
output had valid compatible seeds before truncation, but 16 of those 17 had no
compatible seed in the retained 512. Their best compatible seed ranks were
532--1,794. The one exception, reference 10, had 93 retained compatible seeds
and still lacked a complete output, so later association and consolidation are
also material.

The cap does not create a uniform early-time bias across every lane. It creates
strong lane-specific temporal concentration: 22 of the 80 equal-time deciles
across the eight lanes contain no retained seed first endpoint. One lane retains
none after 175.8 s despite observations through 299.6 s, while other lanes
retain late seeds and leave different holes. Missing reference segments occur
throughout the scan, including 1.2--14.8 s and 286.6--299.6 s. The measured
mechanism is global score competition, with time coverage depending on where
high-weight evidence occurs.

One isolated, same-budget time-stratified retention experiment is warranted.
It should retain the existing seed construction and ordering within each time
stratum, reserve deterministic temporal coverage from the same 512 slots, then
fill unused slots from the existing global order. Tracing, beam search, and
hypothesis consolidation should remain unchanged. This audit is not evidence
for promotion: a reference-specific seed is neither necessary (one complete
merge lacked one) nor sufficient (reference 10), and a proposed stratification
must still pass exact component tests, both frozen observation inputs, and a
runtime comparison.

Reproduce from the repository root:

```sh
python3 reports/2026_09_30_arm_curvature_tracks/seed-selection-audit-v1/audit_seed_selection.py \
  --observations reports/2026_09_30_arm_fast_tracks/server-baseline/output/server-observations.tsv \
  --reference-tracks reports/2026_09_30_arm_fast_tracks/server-baseline/output/server-tracks.tsv \
  --comparison reports/2026_09_30_arm_curvature_tracks/host-v2/server-a250.membership.json \
  --tracker-stderr reports/2026_09_30_arm_curvature_tracks/host-v2/server-a250.stderr \
  --comparator-module reports/2026_09_30_arm_curvature_tracks/evaluation/compare_membership.py \
  --tracker-source native/adaptive/tracking/research/curvature_tracks/curvature_tracks.cpp \
  --output reports/2026_09_30_arm_curvature_tracks/seed-selection-audit-v1/audit.json
```

The full per-lane decile counts and per-reference ranks are in `audit.json`.
