# Dual-RX 10 MS/s: 30-second transport duty measurement

User-authorized acquisition completed on 2026-09-12 at approximately 16:26 UTC.
The FPGA-counter duty was **61.560149%** across exactly 30 seconds, starting
at the first returned sample. This is one measurement, not a rate qualification
across different buffer sizes or repeated operating conditions.

| Measurement | Result |
| --- | ---: |
| Sample rate per receiver | 10,000,000 complex samples/s |
| Receivers | RX0 and RX1 simultaneously |
| Exact measurement interval per RX | 300,000,000 source samples / 30 s |
| Received samples in that interval per RX | 184,680,448 / 18.4680448 s |
| Missing samples in that interval per RX | 115,319,552 / 11.5319552 s |
| Received duty | 61.5601493333% |
| Missing fraction | 38.4398506667% |
| Returned buffers | 1,410 |
| Gap-bearing buffers / overflow-flagged buffers | 880 / 880 |
| Full-buffer device span, including last-buffer overshoot | 30.015488 s |
| Host capture/read elapsed, including startup | 30.363864071 s |
| Host elapsed through capture close | 30.431441920 s |
| Transferred IQ, including last-buffer overshoot | 1,478,492,160 bytes |
| End-to-end CI16 payload rate | 48.692490407 MB/s |

The test used physical Ethernet to `192.168.1.20:30431`, serial
`1040005e0b100007100010000bf33a5d4d`, firmware
`v0.49-plutoplus-spf-iq-direct-async-v4`. It used PPU's ordinary ABI-3 metadata
capture with the `raw-complex64` decoder, eight kernel buffers and 131,072
samples per receiver per buffer. This matches the configured scanner buffer
geometry, but does not run the scanner's hopping or classification machinery.
The ordinary dual-RX path is distinct from PPU's single-RX direct-async path.

The LO remained fixed at the pre-existing 2.4 GHz setting. RF bandwidth was
10 MHz, manual gain was 40 dB, and tandem control was HOLD. Thus this measures
transport/sample retention, not Starlink detections or tuning coverage. Full
IQ was transported and decoded; only per-buffer counter evidence was retained.
No IQ files were stored and host compression/writing was not benchmarked.

The acquisition ended after the first complete refill reaching the 30-second
device window. Received intervals and gaps were clipped to that exact window,
so the denominator is not the longer host runtime or 30 seconds of accumulated
received IQ. Startup before the first returned sample is outside the window.
For every adjacent pair, the counter difference exactly matched PPU's
`missing_samples_before`. Independent post-run recomputation confirmed that
received + missing = 300,000,000 samples per receiver.

The existing production acquisition finished before this test obtained its
normal qualification lease. The test also held the PPU serial lock. It did not
pause or reconfigure the production service, and it verified exact restoration
of the original radio settings before releasing ownership. An independent
post-run lock check found no retained radio lease.

This result supersedes any estimate that this particular dual-RX buffer path
would sustain approximately 70 MB/s based on single-RX direct-async evidence.
It does not establish the maximum possible dual-RX throughput with other
buffer geometry or transport implementations.

Evidence: [canonical measurement receipt](receipt.json), including every
returned frame, runtime identity, applied settings and restoration readback.
[Capture reproducer](capture.py) is the exact helper used; rerunning it starts
new RF collection and requires fresh authorization. Offline interval-boundary
checks and post-run counter closure checks passed.
