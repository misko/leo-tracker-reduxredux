# Finite DDR-ring acquisition V1

The production selector may opt only the 10/15/20 MS/s single-RX leg into a
finite 200,000,000-byte device ring. The 2.5/5 MS/s profiles and probability bag
are unchanged. `LEO_DDR_RING_MAX_RATE_HZ` defaults to `0` (off); reviewed staged
values are `10000000`, `15000000`, and `20000000`. The selector chooses new
`*-ddr-ring-v6` profile revisions; it never edits a queued intent or old profile.
Drain queued operations before changing this selector.

## Persisted authority

The canonical tag `DEVICE_BUFFER:DDR_RING_FINITE_200M_V1` is an explicit policy
identifier in the content-addressed profile and capture plan. A typed
`DeviceBufferRequestV1` is derived before admission. Unknown device-buffer tags,
dual RX, non-native high rates, non-integral targets, and wrong refill/storage
geometry fail closed. This uses existing extensible profile tags and timeline
hardware metadata without widening any published profile/plan/manifest schema.

Ring profiles use 1,000,000 samples/refill: 4 MB per single-RX CI16 frame, exactly
50 frames per ring. A nominal 60-second target is 600/900/1,200 returned frames
at 10/15/20 MS/s. The required firmware is
`v0.44-plutoplus-spf-ddr-ring-prefill-v1`; the release-qualified host dependency
is `pluto-plus-utils@f6dfbfab89e3a947f3f97d5800a337a987720d9c`. Its release-local
native metadata runtime must be installed by the ordinary staging script.

## Two clocks, two boundaries

Firmware's finite target counts returned host frames, **not device-time frames**.
Later pressure gaps can therefore make draining the finite target take more than
60 seconds. Acquisition retains exactly the requested 60-second device-axis
window, with truthful zero fill/gap maps. It continues reading and validating the
bounded finite tail without publishing that out-of-window IQ. This intentional
tail drain is separately counted; it is not called a host drop or extra coverage.
The lower-rate peer still records its ordinary 60-second device window.

The first timeline record contains `hardware_metadata.device_buffer_evidence_v1`:
the exact request, firmware terminal status, returned frames/device span,
counter-proven protected prefix, stored samples, and deliberately drained tail.
The manifest hashes the timeline. Both observed counters and the firmware status
must attest the complete protected prefix. Status must be `complete`,
`target_complete`, error zero, and produced=consumed=target. Later gaps are allowed
and publish as degraded recordings, never fabricated continuity.

## Host ingestion

The existing bounded queue feeds a sequential raw CI16/timeline spool owned by
RecordingStore. Compression starts only after the finite ring has drained and
the radio buffer has been closed. Admission reserves an additional full raw
window for overlap with final compressed shards. Replay verifies the raw digest
and frame/byte inventory. Raw files are removed only after verified replay and
durable final shards. Any failure retains the private spool; no enqueue failure
or unproven device endpoint can be published.

Successful ring captures allow a bounded 600-second post-RF compression budget;
ordinary/failure shutdown retains the existing 10-second limit. A stuck consumer
quarantines the bundle and poisons the live supervisor exactly as before.

## Verification and rollout

1. Stage the exact tested commit with its release-local ABI3 runtime. Leave the
   API and workers unchanged: the public recording format has not changed.
2. Pause/drain acquisition, stop its service, and preserve the environment and
   acquisition selector for rollback. Point `LEO_PROFILE_ROOT` at
   `/opt/leo-tracker/current-acquisition/profiles`. Use the optional
   `20-component-environment.conf` drop-in and `/etc/leo/acquisition.env` for this
   path, the exact acquisition `LEO_ACQUISITION_RELEASE_ID`, and the ring rollout
   limit. Do not change the common worker release identity.
3. Run explicitly authorized hardware canaries with the service stopped. The
   hardware test below requires an explicit enable flag, radio ID, rate, RX, and
   duration. Each invocation is bounded to 20 or 60 nominal seconds. Limit the
   entire new-RF campaign to 30 minutes.
4. Verify 10/15/20 MS/s on each radio, then paired 2.5/20 MS/s 60-second dwells,
   alternating the high radio/RX. Require exact prefix and terminal status, no
   host enqueue failures, store verification, and standard analysis products.
5. Enable 10/15 MS/s first, then 20 MS/s after its canaries pass. Resume the normal
   sampler and inspect its first ring-enabled scheduled dwell. Roll back by
   pausing/draining and restoring the old selector/environment; no reflash.

Failed RF captures preserve `capture-failure-stream-N.json` in the unpublished
session spool, including the original error and best available ring status.
Inspect that together with raw-stage metadata before blaming the host or RF.

The PPU pin constrains NumPy to 2.4.x for its Python 3.11 typing support. Numerical
regression gates must pass even though this rollout changes acquisition only.
