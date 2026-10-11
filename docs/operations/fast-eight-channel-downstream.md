# Eight-channel downstream publication repair

## Root cause

The 2026-10-11 19:23 UTC fast scan sealed 6,762 windows and exported GLRT
evidence on channels 1–8. The deployed standard worker accepted that input and
reconstructed tracks, then failed while serializing a channel-7 tracklet:
`PersistentHopTrajectoryTrackletV1.channel` permits only 1–4. The exception
aborted the whole tracking publication before TLE matching and positioning.
The current TLE-review contract inherited the same restriction. Independently,
the CFO overlay renderer allocated four panels and silently omitted upper
channels. Earlier qualification established completion with weak upper-channel
evidence, without exercising upper-channel tracklet publication.

## Repair and compatibility

- Add an eight-channel tracklet V2 and TLE review V3. Preserve existing models.
- Publish tracking V16 in its own namespace. Lower-channel tracklets retain
  their V1 representation; upper-channel summaries explicitly use V2.
- Update the tracking service and review producer together. Keep numerical
  selection, reconstruction, matching and positioning policies unchanged.
- Let readers serve V16 and fall back through historical versions. Update the
  HTTP response union before switching the writer.
- Size the CFO overlay to the observed channel range, retaining the four-panel
  layout for existing lower-band data.

## Qualification and rollout

1. Test contracts, real synthetic trajectory reconstruction, mixed-channel
   serialization, review creation for every channel, storage round trips,
   immutable V15 fallback, upper-channel HTTP responses and visible PNG panels.
2. Replay the sealed input from `fast8-auto-20261011-192322-412c7737-1-lower`
   through the staged standard worker. Do not repeat RF or GLRT.
3. Require tracking, position methods, blind regional, adaptive TLE positioning
   and regional positioning to complete through their public completion ports.
   Scientific abstention is distinct from an execution failure. Retain matched
   c=0/fitted-c diagnostics and report fit separately from location accuracy.
4. Deploy the reader overlay first, then switch the automatic worker's standard
   command. Preserve prior release selectors for rollback.
5. Exercise a bounded 300-second automatic capture using the existing timer,
   capture authority, recorder and watcher. Verify admission without manual
   analysis commands, terminal durability, all five downstream stages, and each
   manifest-listed PNG by HTTP hash and browser image decoding.
6. Restore the normal automatic schedule after bounded verification. Keep the
   capture control and existing stop behavior intact.

Rollback switches the API and standard worker to their prior overlays. V16
outputs remain available on disk and historical V15 outputs are never rewritten.
Do not roll back by editing or deleting scientific publications.

Before the repair, each affected source file matched the pinned worker at
`/opt/leo-b7/a620e14f3-retained-r1/worker/src`.
The qualification receipt directory is
`/srv/bulk/leo/fast8-downstream-qualification-20261011`.

## Verified deployment and replay

Source revision `fbe2e1985d9a93c729d201b3c8a7be7c708b311e` passed 59
component tests, Ruff and diff whitespace checks. Release
`/opt/leo-fast-auto/20261011-r3` contains matching SHA-256 hashes for all seven
changed files in both the API and standard-worker overlays. The API switched
first, followed by the automatic worker on 2026-10-11 at approximately
20:13 UTC. The GLRT worker and numerical policies were retained.

The original sealed scan completed all five standard stages after replay in
three bounded resumable slices. Its V16 product contains 101 tracklets across
all eight channels and 16 TLE reviews, also covering all eight channels.
All 28 PNGs passed HTTP content-type, signature, byte-count and manifest-hash
checks. A browser opened the scan detail, found every expected PNG link and
decoded every corresponding image without JavaScript errors. Historical V15
reading and its 20 PNGs also passed the staged reader compatibility check.
The deployed watcher subsequently marked the recovered original job complete.

This repairs execution and publication; the regional output remains diagnostic.
For the original scan, the matched B3 comparison gives fitted-c RMS 130.43 Hz
versus c=0 RMS 134.75 Hz, with reference errors 202.80 km versus 203.40 km.
The fitted-c B3 solve did not converge. Operational selection therefore used
fitted-c B1 (204.46 km reference error), while c=0 selected B3. The output does
not claim a position fix. A better frequency fit does not establish useful
localization accuracy. Full comparison and eligibility details are retained in
`replay/controlled-c-ablation.json` in the receipt directory.

The explicitly authorized background qualification used the existing automatic
timer, selector, capture authority and recorder for one 300-second capture:
`fast8-auto-20261011-201026-52138b22-1-lower`. All 6,762 planned windows were
delivered and durably sealed into 14 segments, with zero device invalid,
skipped, cancelled or error windows and no capture fault. The deployed watcher
discovered it automatically, processed 3,603 windows through GLRT, skipped
3,159 through the existing fast gate and reconstructed 95 tracklets covering
all eight channels. No manual analysis command or requeue was used for this
new scan. The watcher completed all five stages in three resumable slices of
766.88, 441.86 and 186.98 seconds. The first slice includes indivisible stages
that can exceed the soft 500-second scheduling budget.

Both scans passed the final live HTTP and browser verification: 28 PNGs each,
56 total, with no browser JavaScript errors. The expected set per scan is four
core tracking plots, 16 TLE reviews, three position-method plots, three blind
regional plots, one adaptive TLE map and one regional plot. Verification checks
the exact expected artifact names, source binding, PNG signatures, hashes and
byte counts, then locates and decodes every image in the scan detail UI. Both
tracking products and review sets cover channels 1–8. Both GLRT reports contain
strong detections on every channel and receiver.

The new scan's matched pre-RF-time comparisons retained the same inputs, other
priors and fitting budgets within each stage. All six fits below converged:

| Stage | Fitted-c RMS (Hz) | c=0 RMS (Hz) | Fitted-c reference error (km) | c=0 reference error (km) |
| --- | ---: | ---: | ---: | ---: |
| B3 | 123.24 | 127.37 | 19.25 | 19.14 |
| B4 | 124.58 | 127.39 | 10.98 | 11.24 |
| B4W | 115.98 | 118.40 | 10.09 | 10.14 |

The later operational B7 selections have RMS 108.80 Hz and reference error
6.89 km for fitted-c, versus 118.88 Hz and 5.82 km for c=0. These are reported
separately from the controlled pre-RF-time comparison. The product remains
diagnostic and explicitly does not claim a position fix; the lower frequency
residual is not evidence of better position accuracy.

## Automatic schedule verification

After both scans passed, the two temporary qualification overrides under
`/run/systemd/system` were removed and the original mixed adaptive/fast schedule
and state were restored. Its state file was preserved byte-for-byte.

Runtime verification exposed a separate timer startup defect: the inherited
empty `OnUnitInactiveSec=` reset cleared the earlier `OnBootSec` trigger. An
idle timer could therefore be enabled with no finite next deadline. The
additive `deploy/systemd/leo-fast-scan-timer-startup.conf` override resets the
inherited triggers first, then sets a ten-minute activation trigger and the
existing ten-minute gap after capture completion. It is installed as
`/etc/systemd/system/leo-v052-adaptive.timer.d/zzzzz-fast-v16-startup.conf`.

`systemd-analyze verify` passed. The effective timer is enabled, active and
waiting, with its next run scheduled for 2026-10-11 20:52:52 UTC. The capture
service uses the original shared selector, production configuration and state;
each capture remains bounded to 300 seconds. Capture authority remains running,
and the automatic analysis watcher remains enabled on the qualified release.

Final receipts are `end-to-end-verification.json`, `browser-verification.json`,
`schedule-restoration.json`, `deployment-receipt.json` and
`new-scan-controlled-c-ablation.json` in the qualification receipt directory.
The browser receipt records each image's decoded dimensions and URL. The
schedule receipt includes effective triggers, the startup override hash and
proof that the normal schedule state was preserved.
