# v0.52 persistent flash and adaptive-scan qualification on radio `…003a`

17 September 2026, 02:49–03:05 UTC. User-authorized bounded hardware work.

## Outcome

Radio `104000bac4950008230026001b440a003a` was persistently upgraded over LAN
from `v0.49-plutoplus-spf-iq-direct-async-v4` to
`v0.52-plutoplus-spf-adaptive-scan-v1`. The exact trusted release asset was used:

- DFU SHA-256: `f88c5fe44160f0a09031fb8b68f92b2280022e0f38174845b7edc3a37c26eea2`
- FRM SHA-256: `35bca4f5cfb6f9ec8a32692ceb2b55a20238a38bbff3e40fcd76789b765002a9`
- FIT SHA-256: `1f3ec2b6937e09a349e952a7bcc499a2902043f09f35c51fb0a5d50eb34d5403`
- Source commit: `2da11edf69bba3e193b816da037da13e41c51a4d`

The guarded PPU flash receipt is
`/srv/bulk/leo/v052-radio003a-flash/9f969f69-d29d-4b74-b2a6-b4dd1b612da3.json`.
It records successful source re-attestation, TX quiescence, physical flash guard,
staged hash verification, protected-region verification, exact `mtd3` FIT
readback, reboot disappearance/return, returned serial/firmware/topology, TX-safe
return and ephemeral SSH-key rotation. The rotated key was installed into the
scanner credential.

## Hardware results

All cells used RX0, two Fast Lock targets at 960.0000 and 1190.3125 MHz, CI16,
manual 40 dB gain during the test, exact source counters and host feedback.

| Cell | Dwell / transition budget | Source duration | Retained duty | Complete / skipped / invalid / cancelled | Result |
|---|---:|---:|---:|---:|---|
| 15 MS/s control | 240 / 10 ms | 20 s | 95.8877% | 79 / 0 / 0 / 0 | passed |
| 20 MS/s overload integrity | 240 / 10 ms | 60 s | 64.9853% | 162 / 77 / 0 / 0 | passed; whole visits skipped |
| 20 MS/s scanner geometry | 120 / 20 ms | 300 s | **85.4870%** | **2137 / 0 / 0 / 0** | passed |

The sustained 20 MS/s scanner-geometry cell delivered 5,128,800,000 valid
samples and 20,515,200,000 IQ bytes across a 5,999,509,092-sample source span.
Thirty-eight feedback messages were accepted and 37 were acknowledged as
applied before terminal completion. Target visit counts were 953 and 1184.
The radio restored its original 30.72 MS/s rate, 18 MHz bandwidth, slow-attack
gain mode, 2.4 GHz LO, four kernel buffers and inactive Fast Lock state. The
instantaneous slow-attack gain readback can move by 1 dB while AGC remains active.

## What fixes the old 20 MS/s duty failure

The former host-adaptive path averaged about 18.6% complete 120 ms duty. Raw
coverage was much higher, but scattered block loss invalidated most visits.
v0.52 owns visit scheduling and admission on the radio and transports complete
visits with explicit skip records. With a truthful 20 ms transition allocation,
120 ms of IQ is produced every roughly 140 ms. The average one-RX CI16 payload is
therefore about 68.6 MB/s rather than a continuous 80 MB/s, which fits this
measured network path. This yielded 85.49% full-session retained duty, close to
the geometric ceiling of 120/140 = 85.71%.

The 240 ms / 10 ms overload cell deliberately asks for about 76.8 MB/s average.
It remained scientifically clean by returning 162 intact visits and 77 explicit
capacity skips, producing 64.99% retained duty instead of fragmenting most visits.

## Integration findings

The current production acquisition release does not yet use the v0.52 `SCANCAPS`,
`OPENM`, `READSCAN`, `SCANFEEDBACK` and `SCANACK` interface. It was restarted
successfully after testing and currently runs its configured conventional 2.5
MS/s scanner profile. A host integration is required to obtain the v0.52 duty
gain in scheduled adaptive scans and persist its visit/feedback evidence in the
normal web products.

Two details must be handled in that integration:

1. A 10 ms transition budget was not stable for this radio/frequency pair at
   120 ms dwell. Fast Lock recall occasionally completed after the declared
   boundary and firmware correctly failed the session with `-ETIME`. A 20 ms
   budget completed 300 seconds without an error.
2. Deadline/failure cleanup may emit a `CANCELLED` record with a zero-length
   valid interval. The existing PPU qualification accumulator incorrectly
   requires every record, including cancelled records, to contain a full dwell.
   The wire record and terminal accounting remained internally consistent; the
   host validator should recognize the cancelled form.

At 120 ms dwell, feedback after every visit and every eighth visit both reached
the same 10 ms Fast Lock timing failure before the guard was increased. Feedback
was not the source of `-ETIME`. The successful cell sent feedback every eighth
complete visit; host code should retry transient `REJECTED` receipts and use
application acknowledgements as the authority for when a new weight took effect.

Release scope is RX0 at fixed 10/15/20/30 MS/s per session. RX1, dual-RX,
60 MS/s and per-visit sample-rate/clock changes remain outside v0.52.
