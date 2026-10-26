# A small recorded-IQ replay is feasible to prepare, but not yet qualified

This check follows the preceding two-export metadata inventory. It examines
one original DS24-0011 chunk through its frozen dataset manifest and records
the distinction between file availability, payload integrity and detector
parity. No IQ is read or decompressed, no detector is run and no position is fit.

The original 10 MS/s recording is present under the `leo` service account.
Ordinary workspace-user access fails at the service-owned directory; a
noninteractive read-only `sudo -u leo` check succeeds. No permissions or service
state were changed. The segment manifest and 64-window index match their
published dataset hashes. The compressed payload exists at its declared
77,511,985 bytes. Its declared uncompressed size is 102,400,000 bytes; the
first paired 20 ms window contains 200,000 complex samples per receiver and
1,600,000 bytes total. Payload hashes remain unverified in this metadata check.

The current public `ShortWindowReader.windows(start_sequence, stop_sequence)`
port can request a bounded range. Its implementation reads and verifies the
entire containing compressed chunk, then verifies per-window bytes and the
complete decompressed chunk as the iterator is exhausted. A future one-window
export must therefore budget one whole chunk and exhaust that bounded iterator;
stopping immediately after the first yield would omit the final chunk checks.
This does not require processing the entire five-minute recording.

The current repository exposes `VerifiedFastWindow` with a sample-rate field
and `production_glrt` accepting its explicit sample rate. The 10 MS/s route
uses `FastScanPolicyV2`, and an existing interface test checks that it bypasses
the 2.5 MS/s predictor. The older DS18 replay utility explicitly selects only
2.5 MS/s and is not a drop-in DS24 replay. Current source availability is not
proof of parity with the historically deployed detector; the working tree
also contains unrelated acquisition edits. Before any selection-bias claim,
bind a frozen detector implementation and replay an unmodified archived window
against its saved candidates. No such parity run occurred here.

There is one additional metadata fact: the raw window index contains paired
receiver **whole-window power summaries**, unlike the inspected derived
tracking exports. For the first window they report approximately -40.51 and
-41.62 dBFS, zero clipped samples and per-receiver sample counts. These are
digital full-scale aggregate powers, not calibrated source-specific received
power, a measured antenna pattern, or a satellite bearing. They can support
clipping/gain diagnostics after the relevant detector/receiver mapping is
verified. This check does not add them as independent position observations.

The next possible bounded action is one hash-verified original-window export
and frozen-detector parity test, followed only if justified by an explicit
clean/weak/crossing injection protocol. Noise-only status and an appropriate
injection waveform are not established by these metadata. Missing detector
parity or signal/noise authority would stop that branch. No new RF collection
is proposed.

[Read-only extraction](replay_availability.py) and
[final metadata result](replay_availability_with_power.json) preserve paths,
hashes, sizes and the small power summaries. The initial
[availability-only result](replay_availability.json) is retained. The first
exploratory export accidentally printed the large probe list before output
truncation; subsequent reads extract only selected metadata. The successful
bounded extractions each take less than one second. This preparation changes
no algorithm, scientific observation or acceptance decision.
