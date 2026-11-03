# ARM longest-missing seed audit

This read-only audit reconstructs the exact seed enumeration and 512-seed cap
used by the frozen v8 curvature tracker on the ARM observations. It joins ARM
and maintained server evidence only through the canonical
`(visit, receiver, probe)` maps. Candidate and source-group digests are not
compared across detector sides. The physical ARM output is byte-identical to
the evaluated host output (`1d0dccd...`).

The audit reproduces the physical counters exactly: 8 lanes, 2,991 source
groups, 18,740 pairs considered, and 4,096 retained seeds. It finds 12,197
valid seeds before the caps.

After excluding nine reference segments represented completely through merged
outputs, 17 maintained reference segments are not reproduced as complete ARM
segments. This is a segmentation comparison, not physical identity truth. Six
have sufficient ARM input coverage under the frozen comparator and 11 are
input-limited. All 17 have at least one compatible valid ARM seed before
truncation. Thirteen retain one or more; only four lose every compatible seed at
the cap:

- Input-supported references 19, 33, and 59 have best compatible ranks 975,
  623, and 549.
- Input-limited reference 47 has best rank 1,045.

Thus seed truncation is a concrete mechanism for three input-supported
maintained-segmentation mismatches, but it is not the main explanation for all
17. The other three input-supported mismatches retain seeds: reference 2 retains
43, reference 10 retains 87, and reference 35 retains 5. Their maintained
segments cease to be distinct later during association, beam selection, or
consolidation. Ten of the 11 input-limited references also retain a seed, but a
seed policy cannot restore evidence that the ARM detector did not supply across
enough of the reference support.

Reference 10 must not be labeled an ARM error from this membership comparison.
Root's independent counterfactual fit found that the pre-branch quadratic over
36--48 s predicts the future reference-16 continuation at 53--61.5 s with about
153 Hz RMS, versus about 5,392 Hz for the reference-10 tail; 38--50 s and
40--52 s windows give the same conclusion. The ARM tracker follows the locally
smoother continuation, while the maintained server output switches global
linear segment identity. The 87 retained seeds rule out seed starvation for
reference 10, but the disagreement does not identify which segmentation is the
physical object.

The requested longest-missing references compare as follows. `rank` is the
one-based position in the existing per-lane global seed order before truncation.

| ref | ARM input status | ARM valid | ARM retained | ARM best rank | server retained | server outcome |
|---:|---|---:|---:|---:|---:|---|
| 2 | supported | 106 | 43 | 31 | 29 | complete one-to-one |
| 10 | supported | 358 | 87 | 14 | 93 | missing |
| 30 | input-limited | 21 | 13 | 334 | 0 | missing |
| 8 | input-limited | 7 | 6 | 271 | 0 | missing |
| 34 | input-limited | 58 | 50 | 17 | 96 | complete one-to-one |
| 47 | input-limited | 9 | 0 | 1,045 | 0 | missing |
| 19 | supported | 32 | 0 | 975 | 0 | missing |
| 59 | supported | 62 | 0 | 549 | 0 | missing |
| 33 | supported | 57 | 0 | 623 | 0 | missing |

References 19, 33, and 59 are the strongest cases for the already proposed
same-budget time-stratified seed experiment because both detector inputs contain
compatible seed opportunities and both global caps discard them. References 2
and 10 establish that retaining many compatible seeds is insufficient to
reproduce the maintained segmentation; reference 10 also demonstrates why that
segmentation must not be treated as physical identity truth.
Reference 34 separates detector coverage from seeding: the server input is
complete and reconstructs it, while ARM is input-limited despite retaining 50
compatible seeds.

No algorithm or primary configuration changed. A future seed-retention
experiment should preserve seed construction, score ordering inside each
stratum, tracing, beam search, and consolidation, and should be assessed
separately from the input-limited references.

The full per-reference and per-lane data are in `audit.json`. The companion
`server-seed-audit.json` recomputes the server-side seed audit against the same
frozen v8 source rather than the subsequently edited research worktree.

Reproduce the ARM audit from the repository root:

```sh
python3 reports/2026_09_30_arm_curvature_tracks/longest-missing/arm-seed-audit/audit_arm_seeds.py \
  --observations reports/2026_09_30_arm_fast_tracks/server-baseline/output/arm-observations.tsv \
  --observation-source-map reports/2026_09_30_arm_fast_tracks/server-baseline/output/arm-candidate-map.tsv \
  --reference-observations reports/2026_09_30_arm_fast_tracks/server-baseline/output/server-observations.tsv \
  --reference-tracks reports/2026_09_30_arm_fast_tracks/server-baseline/output/server-tracks.tsv \
  --reference-source-map reports/2026_09_30_arm_fast_tracks/server-baseline/output/server-candidate-map.tsv \
  --comparison reports/2026_09_30_arm_curvature_tracks/host-v2/arm-a250.membership.json \
  --tracker-stderr reports/2026_09_30_arm_curvature_tracks/physical-arm-a250.log \
  --physical-output reports/2026_09_30_arm_curvature_tracks/physical-arm-a250.tsv \
  --comparator-module reports/2026_09_30_arm_curvature_tracks/evaluation/compare_membership.py \
  --tracker-source reports/2026_09_30_arm_curvature_tracks/research-v2/source/curvature_tracks.cpp \
  --research-receipt reports/2026_09_30_arm_curvature_tracks/research-v2/receipt.json \
  --server-seed-audit reports/2026_09_30_arm_curvature_tracks/longest-missing/arm-seed-audit/server-seed-audit.json \
  --output reports/2026_09_30_arm_curvature_tracks/longest-missing/arm-seed-audit/audit.json
```
