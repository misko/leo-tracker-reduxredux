# Receiver marker colors deployed

PR #50 was merged and release `5651560e645cac11f4073a1ddde7dd8bfd3873ca`
was staged with the standard immutable-release builder on 2026-09-27.
All 17 adaptive analysis workers (instances 0–16) now run that release through
`/etc/systemd/system/leo-adaptive-analysis-worker@.service.d/99-rx-marker-colors.conf`.
The prior `80-immutable-release.conf` remains unchanged for rollback.

The production source delta from the former adaptive worker release `2c30eaf5`
is only `leo.presentation.adaptive_hop_analysis`: lower RX0/RX1 are blue/orange,
upper RX0/RX1 purple/green, and association lines match their markers.
Existing immutable published images retain their original bytes; new renders
use this palette. API, acquisition, ordinary workers, and component selectors
were not changed.

Validation: exact merged-revision tests, full source mypy, lint, and formatting
passed. The standard builder validated source identity, native runtime, and
sealed publication metadata. Worker 0 was restarted and checked first, followed
by the remaining workers. All 17 running process command lines were verified;
the deployed Python imports the four-color renderer. The live API status
endpoint on port 8090 returned HTTP 200. See [deployment evidence](deployment.json).

The first staging attempt stalled amid bulk-filesystem writeback pressure.
Its unpublished build was removed by the standard cleanup. A competing
read-only corpus search was temporarily paused with a timed-resume safeguard,
then explicitly resumed once staging succeeded. No search work was discarded.

Rollback: remove only `99-rx-marker-colors.conf`, run `systemctl daemon-reload`,
and restart the 17 adaptive analysis worker instances listed in the evidence.
This restores the still-present previous immutable worker binding.
