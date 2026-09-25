# RX0-only 10 MS/s: 30-second transport duty measurement

The user-requested single-RX comparison completed on 2026-09-12 at approximately
16:29 UTC with **100% measured duty**, zero missing samples, zero gap events,
and zero overflow flags.

| Measurement | RX0 only | Earlier RX0 + RX1 |
| --- | ---: | ---: |
| Configured sample rate per RX | 10 MS/s | 10 MS/s |
| Exact FPGA measurement window | 30 s | 30 s |
| Received sample time per RX | 30 s | 18.4680448 s |
| Missing sample time per RX | 0 s | 11.5319552 s |
| Counter-observed duty | 100% | 61.5601493333% |
| Offered CI16 payload | 40 MB/s | 80 MB/s |
| Measured payload, including startup | 39.757849824 MB/s | 48.692490407 MB/s |
| Gap events | 0 | 880 |

The same Pluto (`192.168.1.20:30431`, serial
`1040005e0b100007100010000bf33a5d4d`), deployed host runtime, ordinary ABI-3
metadata capture, raw-complex64 decoder, eight kernel buffers, and 131,072
samples per buffer were used for both runs. The single-RX run enabled only RX0.
The fixed LO remained 2.4 GHz, bandwidth was 10 MHz, gain was manual 40 dB,
and tandem mode was HOLD. No scanner hopping or classification ran.

All 300,000,000 samples in the exact 30-second window were received. The
measurement returned 2,289 complete buffers, spanning 30.0023808 seconds of
FPGA time and transferring 1,200,095,232 IQ bytes. The last buffer was clipped
to the exact window for duty calculation. Host capture/read elapsed was
30.185114067 seconds, including first-frame startup; capture close finished
at 30.251323706 seconds. Time before the first returned FPGA sample is outside
the duty window.

An independent post-run calculation reproduced the 100% result from every
frame counter, verified every adjacent counter closure, confirmed RX0-only
readback, and confirmed exact restoration of the original dual-RX settings.
The normal production qualification lease and PPU serial lock were held only
for the test and released afterward. Production capture remained enabled and
its service remained running.

Full IQ was transferred and decoded, but only metadata was retained. This is
a fixed-tuning, 30-second transport result; it does not qualify a 300-second
hopping run, long-term operation, disk compression, or the direct-async path.

Evidence: [receipt with per-buffer counters](receipt.json),
[exact acquisition helper](capture.py), and the
[dual-RX comparison](../2026_09_12_dual_rx_10msps_30s/README.md).
Rerunning the helper starts a new RF collection and requires fresh authorization.
