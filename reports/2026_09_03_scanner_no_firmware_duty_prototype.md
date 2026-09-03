# Scanner duty-cycle prototype without FPGA or firmware changes

## Outcome

The existing radio can exceed 90% integrity-attested RF listening duty at both
scheduled sample rates without FPGA or firmware changes. A radio-local capture
prototype keeps the exact current ABI-3 metadata provider's sampler threads
warm, releases device ownership around each volatile AD9361 Fast Lock recall,
and starts a new independently attested stream for every 120 ms target visit.
The 300-second qualification measured 92.288% at 2.5 MS/s and 92.262% at
5 MS/s, with zero startup discards, gaps, or overflow flags.

This qualifies the radio-local capture core, not yet a production scanner
path. Concurrent Ethernet transport, durable persistence, cancellation, and
supervised recovery remain to be integrated and measured. The ordinary-DMA
timing ceiling remains 97.17% at 2.5 MS/s and 96.63% at 5 MS/s.

No FPGA bitstream, firmware image, boot configuration, or persistent radio
file was changed during this work.

## Test boundary

- Radio route: `192.168.1.18`
- Serial: `1040007c4a94000211000b009186843ef2`
- Explicitly excluded serial: `104000bac4950008230026001b440a003a`
- Firmware observed: `v0.49-plutoplus-spf-iq-direct-async-v4`
- Target order: `CH1L CH2L CH3L CH4L CH1U CH2U CH3U CH4U`
- Dwell: 120 ms per target
- Rates and RF bandwidths: 2.5 MS/s + 2.5 MHz; 5 MS/s + 5 MHz
- Gain: manual 40 dB during each canary
- Short-run C results: 32 targets, four complete sweeps per rate
- Long-run C result: 2,500 targets and exactly 300.000 requested listen
  seconds per rate
- Total new RF time: bounded below 30 minutes

The radio started and ended at the same complete settings readback:
30.72 MS/s, 18 MHz bandwidth, 2.4 GHz LO, slow-attack gain on both receivers,
71 dB gain readback on both receivers. RX Fast Lock was inactive after the
test. All temporary radio files and the temporary alternate `iiOD` process
were removed.

## Results

| Path | Integrity status | 2.5 MS/s duty | 5 MS/s duty |
| --- | --- | ---: | ---: |
| Ethernet metadata, one 120 ms buffer | ABI-3 attested | 23.20% | 15.84% |
| Ethernet metadata, 12 × 10 ms host batch microbenchmark | ABI-3 attested, 8/8 targets contiguous | 44.55% | 38.33% |
| Leo adapter, 12 × 10 ms host batch | ABI-3 attested, 8/8 targets contiguous | 29.28% | 26.10% |
| Radio-loopback `iiOD`, one 120 ms metadata buffer | ABI-3 attested, 64/64 frames valid | 30.99% | 28.00% |
| Radio-local ordinary DMA, one 120 ms buffer + Fast Lock | Timing ceiling only | 92.48% | 87.91% |
| Radio-local ordinary DMA, 12 × 10 ms refills + Fast Lock | Timing ceiling only | **97.17%** | **96.63%** |
| Radio-local metadata, provider reopened every dwell | ABI-3 attested, 768/768 subframes valid | 64.68% | 64.67% |
| Radio-local metadata, provider reused across dwells | ABI-3 attested, 60,000/60,000 subframes valid | **92.29%** | **92.26%** |

### 300-second timing canary

The winning local ordinary-DMA path was repeated for exactly 2,500 120 ms
target visits per rate, or 300.000 seconds of requested listening at each
rate. Every visit completed and every refill returned its exact expected
payload size. The run covered 312 complete eight-target sweeps plus CH1L
through CH4L of the next sweep per rate.

| Rate / RF bandwidth | Listen | Wall | Duty | Whole-target p95 / max |
| --- | ---: | ---: | ---: | ---: |
| 2.5 MS/s / 2.5 MHz | 300.000 s | 308.668 s | **97.192%** | 123.670 / 124.638 ms |
| 5 MS/s / 5 MHz | 300.000 s | 310.367 s | **96.660%** | 124.360 / 125.678 ms |
| Combined | 600.000 s | 619.034 s | **96.925%** | — |

The radio was restored to the exact pre-run readback: 30.72 MS/s, 18 MHz
bandwidth, 2.4 GHz LO, slow-attack gain on both receivers, and 71 dB gain on
both receivers. The temporary radio executable was removed. The machine-
readable result is
`reports/figures/2026_09_03_scanner_300s_canary/raw_300s_per_rate.json`.

This passes the 300-second duration and timing-duty portion of the canary. It
does **not** close the production qualification gate: ordinary local DMA has
no atomic ABI-3 metadata, device/FPGA counter attestation, Ethernet transport,
durable persistence, or backpressure exercised by this test.

### 300-second integrity-attested canary

The optimized radio-local metadata path was also run for 2,500 target visits
at each rate. It used the exact provider and metadata sources corresponding to
the installed v0.49 image, two kernel buffers, and twelve independently
validated 10 ms refills per target. The provider session was opened once per
rate; device ownership and the DMA buffer were released between targets so the
Fast Lock recall never raced an active capture. A fresh stream ID and sequence
origin explicitly excluded each hop-transition interval from both neighboring
channels.

| Rate / RF bandwidth | Accepted signal | Wall | Duty | Whole-target p95 / max |
| --- | ---: | ---: | ---: | ---: |
| 2.5 MS/s / 2.5 MHz | 300.000 s | 325.070 s | **92.288%** | 130.088 / 137.988 ms |
| 5 MS/s / 5 MHz | 300.000 s | 325.160 s | **92.262%** | 130.078 / 138.919 ms |
| Combined | 600.000 s | 650.230 s | **92.275%** | — |

All 5,000 target visits and all 60,000 metadata-bearing subframes completed.
Every record passed CRC, stream identity, buffer sequence, payload geometry,
hardware sample-counter continuity, zero-missing-sample, and zero-overflow
checks. The test covered 624 complete eight-target sweeps plus four targets of
the next sweep at each rate and touched 18 GB of IQ payload without persisting
it. The machine-readable result is
`reports/figures/2026_09_03_scanner_300s_canary/raw_local_provider_reuse_300s_per_rate.json`.

The radio was restored to the exact pre-run settings: 30.72 MS/s, 18 MHz
bandwidth, 2.4 GHz LO, slow-attack gain on both receivers, and 71 dB gain on
both receivers. This passes the radio-side duration, integrity, and 90% duty
gate. It does not yet qualify network transport or durable storage.

A same-day repeatability run covered another 300.000 accepted seconds at each
rate. It measured 325.050 seconds wall time and 92.293% duty at 2.5 MS/s, then
325.110 seconds wall time and 92.276% duty at 5 MS/s. Combined duty was 92.285%.
All 5,000 visits and 60,000 metadata-bearing subframes again passed with zero
startup discards. An independent post-run readback confirmed the same complete
restored radio state, and the temporary executable was removed. The raw result
is
`reports/figures/2026_09_03_scanner_300s_canary/raw_local_provider_reuse_300s_per_rate_rerun.json`
(SHA-256
`6937038a7dee608dbb1c86747863dda80303f9979d13a02dd7b7180ae51a4fa1`).

The two host-batch figures measure different boundaries. The microbenchmark
times only the isolated per-target stages; the Leo adapter result includes the
production reset, anchoring, mapping, and adapter lifecycle. The adapter still
preserved the existing output shape, returned unique stream generations, and
reported no missing samples or overflows.

### Winning local stage timing

| Stage mean per target | 2.5 MS/s | 5 MS/s |
| --- | ---: | ---: |
| Fast Lock recall | 0.197 ms | 0.185 ms |
| Buffer create | 1.787 ms | 2.457 ms |
| Twelve refills, total | 120.477 ms | 120.471 ms |
| Sparse payload touch | 0.020 ms | 0.020 ms |
| Buffer destroy | 0.641 ms | 0.677 ms |
| Whole target | 123.499 ms | 124.186 ms |

Smaller buffers are therefore material. Against a full 120 ms local buffer,
they gained 4.69 percentage points at 2.5 MS/s and 8.71 points at 5 MS/s. Fast
Lock was also material: ordinary full-buffer frequency writes produced only
85.79% and 81.80%, while the same full-buffer path with Fast Lock produced
92.48% and 87.91%.

## Integrity findings

The loopback metadata canary read 64 frames. Every frame passed metadata CRC,
payload geometry, scan-mask, hardware-counter-valid, zero-gap, zero-overflow,
buffer-sequence-zero, and unique-stream checks. Its poor duty proves that
process placement alone is insufficient when every buffer still traverses the
serialized `iiOD` request/response path.

The first alternate `iiOD` build selected the kernel-device hop provider and
therefore correctly refused to advertise `iio,buffer-persistent-hop`: the
current v0.49 image does not expose `ADI_PERSISTENT_HOP_IOC_GET_CAPS`. The
subsequent no-firmware executor instead uses the already-present tandem
ownership/counter ABI together with conventional AD9361 Fast Lock attributes.
It admits a session only after attesting all eight recalled LO profiles, keeps
hop scheduling beside the radio DMA loop, and restores the conventional LO
path exactly on every exit. It does not emulate or claim the absent kernel hop
ABI.

The local ordinary-DMA ceiling has no atomic metadata sidecar. It proves that
Fast Lock plus 10 ms refills can meet the timing goal, but it cannot satisfy
the current scanner continuity contract and must not be used for production
recordings as-is.

## Implemented safe increment

The host path now requests a bounded 12-frame metadata batch for the qualified
120 ms geometries. Each 10 ms ABI-3 subframe is independently checked for
stream, buffer sequence, FPGA sample-counter continuity, missing samples,
overflow, shape, and timing evidence before the unchanged 120 ms scanner block
is assembled. Unqualified rate/dwell geometries keep the one-buffer behavior.

The paired `pluto-plus-utils` change exposes a validated `batch_frames` option,
limits it to 1..64, scales the bounded timeout, and rejects incompatible DDR or
direct-async combinations.

## Recommended next gate

Do not deploy either standalone prototype as the scanner. The no-flash
radio-local metadata capture core now passes the atomicity, continuity,
hop-exclusion, success-restoration, duration, and radio-side duty gates. It
must be integrated with a bounded sender and separate host writer, then pass
the remaining production gates:

1. Concurrent Ethernet transfer and durable host persistence with bounded
   backpressure.
2. Exact radio restoration on cancellation, disconnect, and sink
   failure.
3. A persisted 300-second canary at each rate with at least 90% valid
   device-counter duty and end-to-end artifact validation.

## Continuous Ethernet userspace-hop canary

The no-flash userspace hop executor subsequently completed one full 2.5 MS/s,
2.5 MHz Ethernet canary with a 5 ms post-transition guard.  The device-counter
span was 300.067 seconds, of which 277.440 seconds were complete 120 ms valid
visits: **92.4594% valid duty**.  All eight targets received exactly 289
visits.  The host accepted 5,724 contiguous ABI-3/HOPS frames (6,002,049,024
IQ bytes) with zero missing samples, overflows, or hop-event sequence gaps.
HOPT reported normal completion and restoration; an independent connection to
the stock daemon then confirmed the exact original 30.72 MS/s, 18 MHz, 2.4 GHz,
dual slow-attack/71 dB settings and inactive Fast Lock state.

This closes the continuous Ethernet transport and 300-second/90% timing gate
at 2.5 MS/s.  The sink deliberately discarded IQ after validation, so durable
persistence and the 5 MS/s rate remain separate gates.  The result is recorded
in
`reports/figures/2026_09_03_scanner_300s_canary/userspace_hop_ethernet_300s_2p5m.json`.

The matching 5 MS/s / 5 MHz run then completed a 300.034-second device span
with 276.960 seconds of valid visits: **92.3095% valid duty**.  It delivered
2,308 ordered visits, zero missing samples, zero overflow, zero event-sequence
gaps, and an exact host restoration receipt.  The per-target counts were
289 for CH1L..CH4L and 288 for CH1U..CH4U, the expected one-visit bounded
difference at the terminal envelope.  Its machine-readable result is
`reports/figures/2026_09_03_scanner_300s_canary/userspace_hop_ethernet_300s_5m.json`.

Together these two runs close the continuous Ethernet 300-second/90% timing
and integrity gate at both scheduled rates.  Both still used a validation-only
discard sink; durable queued publication remains the next production gate.

## Durable 300-second 2.5 MS/s canary

The production-like queued store subsequently captured, published, and fully
re-read a 300-second 2.5 MS/s / 2.5 MHz session from the permitted
`192.168.1.18` radio. The device-counter envelope was 750,222,209 samples, with
694,200,000 valid samples in 2,314 complete visits: **92.5326% valid duty**.
Target coverage was balanced to within one visit (289 or 290 visits per
target). There were zero missing samples, overflows, or hop-event sequence
gaps, and HOPT plus independent sysfs readback confirmed exact restoration.

The first persisted attempt exposed a real backpressure limit rather than
masking it: the 16-visit host queue filled, stopped refills long enough to
exhaust all eight radio kernel buffers, and the daemon failed closed on the
resulting full-block counter gap. A 64-visit queue completed with a measured
high-water mark of only two visits, a maximum enqueue wait of 3.03 ms, and no
enqueue failures. A separate preflight failure also identified incorrect
ownership of the new publication namespace; the namespace is now owned by the
production `leo` account, and the canary rejects unwritable spool or bundle
roots before starting RF.

The final store contains 290 zstd chunks, 5,553,600,000 uncompressed IQ bytes,
and 1,130,623,841 compressed bytes. Every compressed and uncompressed chunk
digest was verified in 5.29 seconds after a 303.68-second capture/publication
lifecycle. The published session is
`canary-hop-20260903T063640Z-2p5m` at
`bulk://scanner-hop-recordings/2026/09/03/canary-hop-20260903T063640Z-2p5m`;
manifest SHA-256 is
`84338517f5e4dc6d1d25b630fe4b533da87bfcf36c9e374a0c117eaf9ce24780`.
The live scanner history API returns it as complete, continuous, restored, and
qualified. Full GLRT/CFO analysis remains explicitly pending a bounded
backpressure-aware analysis worker.

The source-level timing prototype is
`tools/prototype_pluto_local_metadata_scanner.c`. Its default mode tests
loopback ABI-3 metadata. `ordinary-local` measures full-dwell local DMA, and
`ordinary-local-small-buffer` measures twelve 10 ms refills. It hard-refuses
any serial except the authorized test radio.

## Durable 300-second 5 MS/s canary

The matching production-like 5 MS/s / 5 MHz durable canary completed after
adding a bounded eight-visit host read-ahead between PPU visit assembly and
storage. The device-counter envelope contained 1,500,626,962 samples, of which
1,385,400,000 were valid samples in 2,309 complete 120 ms visits:
**92.3214% valid duty**. Target coverage was balanced to within one visit
(288 or 289 visits per target) in the required CH1L, CH2L, CH3L, CH4L, CH1U,
CH2U, CH3U, CH4U order. The receipt reported zero missing samples, zero
overflows, zero event-sequence gaps, continuous capture, normal completion,
and exact restoration.

The storage queue reached a high-water mark of two of 64 visits, incurred no
enqueue failure, and had a maximum enqueue wait of 30.6 microseconds. Capture
and publication took 302.63 seconds; a complete post-publication decompression
and digest pass over all 289 chunks took another 14.04 seconds. The published
bundle contains 11,083,200,000 uncompressed IQ bytes and 2,447,804,426
compressed bytes at
`bulk://scanner-hop-recordings/2026/09/03/canary-hop-20260903T070800Z-5m-readahead8`.
Its manifest SHA-256 is
`e29217b63c45e0945cb30897e70898c5617490a4213b407b1cad2270686c2fe7`.

The live scanner-history API exposes the session as complete, qualified,
continuous, and restored. Independent stock-iiOD readback after the run
confirmed the original 30.72 MS/s sample rate, 18 MHz RF bandwidth, 2.4 GHz
LO, and dual slow-attack/71 dB gain state. The exact attested alternate iiOD
process was then stopped, its three exact `/tmp` artifacts removed, port 30432
confirmed closed, and the stock endpoint re-probed healthy. No firmware or
FPGA image was changed.

A subsequent full production-radio lifecycle canary ran as the `leo` service
account with systemd-delivered credentials on `radio_pluto_5d4d` at
`192.168.1.20`. It captured 300 nominal seconds at 5 MS/s and 5 MHz RF
bandwidth with the release's 5 ms transition guard. The device-counter
denominator was 1,500,190,857 samples, of which 1,384,200,000 were valid:
**92.2683% valid duty** across 2,307 visits. All 289 durable chunks were
decompressed and digest-verified; missing samples, overflows, hop-event gaps,
and storage enqueue failures were all zero. The radio was restored exactly,
the owned userspace iiOD was removed, port 30432 was closed, the stock endpoint
was healthy, and acquisition plus all 20 workers were restored. The live API
reports the session as complete, qualified, continuous, and restored. The
machine-readable evidence is
`reports/figures/2026_09_03_scanner_300s_canary/userspace_hop_production_lifecycle_300s_5m.json`.

This canary also closed two release-admission defects in the pinned
`pluto-plus-utils` lifecycle before RF was allowed: it now selects the local
iiOD backend explicitly and waits within a bounded deadline for the newly
spawned listener, and it accepts only root-owned mode-0440 credentials beneath
systemd's `/run/credentials` namespace in addition to process-owned private
files. The release pins revision `5790a39705e9e598ef048ec773e0227cf9ac1808`.
