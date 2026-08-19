# Trusted matched-recovery V2 producer

This WP11 lane is selected explicitly and is never part of standard/default
processing. Its fixed DAG is:

1. `native-known-pilot-evidence` produces the release-local schema-2 native
   evidence product; then
2. `trusted-matched-recovery-v2` consumes that exact same-run/scope product and
   publishes `starlink.trusted-matched-recovery` schema 2.

The second stage replays `evaluate_trusted_matched_recovery_v2`. The artifact is
content evidence only: its receipt always retains `acceptance_eligible=false`
and `production_accepted=false`. A later trusted-campaign outer authority must
independently reload its catalog dependency, recording, calibration, release,
legacy receipt, and durable digests before making any campaign-level claim.

The selected composition admits only the concrete PostgreSQL calibration scope,
the concrete pinned RecordingStore and AnalysisArtifactStore on the same retained
root inode, the exact digest-verifying RecordingIqReaderProvider, deployed release
validator, release-local native executor, and a retained-directory-FD legacy oracle
authority. Upstream selection requires one available scientific/complete product
from the exact native stage and same run/scope; a same-kind product from another
stage is not authority. The recording is fully digest-verified before calibration
resolution, and a caller-supplied IQ implementation is rejected. The legacy receipt is
opened as one mode-0440, single-link regular file beneath the retained local
directory capability, and its whole-stream IQ digest must equal the exact RX1
recording bytes. Missing mappings, symlinks, changed IQ, mixed run/scope/release
lineage, or any of the 600 decision mismatches fail closed.

This remains an inner content-only producer. Pinned composition and deterministic
dependencies prevent accidental substitution, but do not create a production
acceptance claim. The outer trusted-campaign resolver independently reexecutes the
native worker over RecordingStore IQ before it can promote any result.
