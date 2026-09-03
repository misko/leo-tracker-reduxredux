# Scanner duty-cycle prototype without FPGA or firmware changes

## Outcome

The existing radio can exceed 90% RF listening duty at both scheduled sample
rates when hopping and DMA acquisition run locally, using volatile AD9361 Fast
Lock profiles and one persistent 10 ms DMA buffer per 120 ms visit. The bounded
prototype measured 97.17% at 2.5 MS/s and 96.63% at 5 MS/s.

That result is a timing ceiling, not yet a production scanner path. The local
Linux IIO backend does not expose the atomic ABI-3 metadata provider, and this
firmware does not expose the persistent-hop kernel ABI. The present
continuity-attested Ethernet path remains well below 90%.

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

Launching the exact persistent-hop-capable user-space `iiOD` from `/tmp` on an
alternate port did not advertise `iio,buffer-persistent-hop`. Source review
and runtime probing agree on the reason: admission requires the
`ADI_PERSISTENT_HOP_IOC_GET_CAPS` kernel device ABI. The current v0.49 image
does not expose it. A userspace binary cannot truthfully claim that ABI merely
by replacing `iiOD`.

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

Do not deploy the ordinary-DMA prototype as the scanner. For a no-flash path,
the next prototype must make the exact current metadata provider callable by a
radio-local capture/sender process, preserve 10 ms buffers and Fast Lock, and
stream completed buffers to a separate host writer. It must then pass, in this
order:

1. ABI-3 metadata and IQ atomicity for every 10 ms refill.
2. Exact buffer and FPGA sample-counter continuity across all twelve refills.
3. Explicit transition-invalid intervals around every Fast Lock recall.
4. Concurrent Ethernet transfer and durable host persistence with bounded
   backpressure.
5. Exact radio restoration on success, cancellation, disconnect, and sink
   failure.
6. A 300-second canary at each rate with at least 90% valid device-counter duty.

The source-level timing prototype is
`tools/prototype_pluto_local_metadata_scanner.c`. Its default mode tests
loopback ABI-3 metadata. `ordinary-local` measures full-dwell local DMA, and
`ordinary-local-small-buffer` measures twelve 10 ms refills. It hard-refuses
any serial except the authorized test radio.
