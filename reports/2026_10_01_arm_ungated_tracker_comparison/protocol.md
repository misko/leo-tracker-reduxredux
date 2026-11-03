# Tracker comparison after coarse-cutoff removal

Run the frozen original rolling, Kalman v2, local tracklet linking v2, and
coarse-seeded curvature binaries on the same 16,191 passing cutoff-disabled
GLRT candidates. Use the completed rolling-backfill result as the fifth
comparison. No parameters, algorithms, GLRT scores, reference fixtures, or
matching thresholds are changed in this comparison.

Use the same full 300-second DS9 scan and frozen maintained server tracklets.
Exclude only the approved ref #10 exception (62 reviewed references). Report
strict >=80% coverage plus >=80% source-purity matching; separately report
coverage-only as a diagnostic, not a replacement correctness criterion.
Also expose one-to-one matching, overlapping hypotheses, and outputs with no
matching source/CFO evidence in any server reference.

Three host repetitions per newly evaluated method must be deterministic.
Three physical PLUTO+ repetitions per method must match host byte-for-byte;
run the physical component test first. Include coarse seed generation and
curvature expansion in the coarse-seeded timing. Reuse unchanged-input
rolling-backfill qualification rather than rerunning it. No RF collection,
firmware change, or production activation.

Inspect references #9, #19, #33, #37, which lost strict agreement under
rolling-backfill with expanded GLRT input, and report remaining coarse-seeded
coverage/purity issues. Interpret merging across server segments explicitly:
any-output segment representation is not one-to-one reconstruction or proven
physical identity.
