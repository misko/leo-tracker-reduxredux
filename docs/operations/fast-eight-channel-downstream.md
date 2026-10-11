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

The staged source matches the pinned worker at
`/opt/leo-b7/a620e14f3-retained-r1/worker/src` for every changed production file.
The qualification receipt directory is
`/srv/bulk/leo/fast8-downstream-qualification-20261011`.
