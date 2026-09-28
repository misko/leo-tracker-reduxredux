# Radio .20 roof location and orientation

Verified recovery: `scan-fw-2e6b78f0cd0cbbbc` completed at 23:35:19 UTC with
2,222 visits, both receiver columns, and a 2.5 MS/s sample rate. Its qualified
first-sample bracket is 23:30:17.758–23:30:18.121 UTC. The first roof companion
was published at 23:38:20 UTC and binds source manifest
`sha256:008a7b873a386e254da5897cdbc15c6641a99667c7f9074e92a407005d999867`.
The existing ten-minute RF timer remains active; the new one-minute timer only
publishes companion metadata. Six focused tests and the installed service check
passed. The existing `.20` importer explicitly had no fixture geometry binding.

The operator moved `.20` to the roof on 2026-09-26, approximately 23:30 UTC,
at latitude 37.849056280893684, longitude -122.48575489722863. Physical RX1
points west and RX2 east. The fixture is identical to the LT3D-001A previously
used by `.21`: nominal mount-reference separation 80 mm, outward tilt 10 degrees.

The [pose authority](../../deploy/station/gauss-r20-roof-20260926-v1.json)
records this evidence. It assumes WGS84 coordinates and geographic cardinal
directions; altitude, actual elevation angles, RF phase centers, and the directed
phase-center baseline remain unknown. Physical connector RX1/RX2 to software
RX0/RX1 is provisional until confirmed. Do not turn the mount separation into a
measured RF baseline or infer horizontal antenna pointing from east/west azimuth.

The conservative validity boundary is 2026-09-26 23:30:17 UTC, the first
inspection after the initial completion report. A later operator statement at
approximately 23:34:50 described the move as complete about five minutes earlier.
The boundary is not a surveyed movement instant. Earlier or overlapping captures
are excluded; old geometry and historical captures are not rewritten.

`leo-adaptive-capture-pose.timer` invokes the
[binder](../../tools/bind_adaptive_capture_pose.py) once per minute. It uses the
installed acquisition release's read-only `AdaptiveHopIqStore` interface,
qualified capture UTC brackets, radio serial, and both receiver IDs. File
publication times do not establish eligibility. The authority file is pinned by
SHA-256. The binder starts no RF recording.

Companions are immutable JSON files in:

`/srv/bulk/leo/capture-pose/gauss-r20-roof-20260926-v1/<session-id>.json`

Each carries the source manifest digest, a complete authority snapshot and its
digest, the capture interval, and its own binding digest. Publication is atomic,
retries verify identical content, and a new pose requires a new revision.
Consumers must verify the source manifest digest before using a companion.
The current tracking/UI code does not yet consume these companions automatically;
this deployment preserves capture-linked evidence for that integration. Existing
IQ manifest versions, fixture contracts, and satellite-association priors are
unchanged.

Deployment uses the exact script-content digest under `/opt/leo-capture-pose/`,
the installed acquisition Python runtime, the authority under
`/etc/leo/station-authority/`, and the two committed systemd unit files. Only the
companion directory is writable to the service. To stop companion publication,
disable `leo-adaptive-capture-pose.timer`; this does not stop adaptive acquisition.

Before another relocation, stop this timer and record the time boundary. The
open-ended current authority is a configuration assumption until superseded;
it cannot detect physical movement automatically. Preserve existing companion
files and add the new pose revision with a disjoint capture-time interval.
