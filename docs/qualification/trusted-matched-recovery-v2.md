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

Production composition admits only the concrete PostgreSQL calibration scope,
the concrete RecordingStore, deployed release validator, release-local native
executor, and a retained-directory-FD legacy oracle authority. The recording is
fully digest-verified before calibration resolution. The legacy receipt is
opened as one mode-0440, single-link regular file beneath the retained local
directory capability, and its whole-stream IQ digest must equal the exact RX1
recording bytes. Missing mappings, symlinks, changed IQ, mixed run/scope/release
lineage, or any of the 600 decision mismatches fail closed.
