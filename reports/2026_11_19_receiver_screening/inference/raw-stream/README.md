# Bounded compressed IQ replay

The bounded reader reduced peak RSS by **56–57%** on matched 64-visit chunks. Both complete replays returned the exact ordinary native factors, graph and compact secant fixes. The saving comes from removing the full compressed-member buffer while authenticating the same stored bytes. [Sealed results](prediction-lock.json) · [Matched reader probes](reader-probe.json)

The archive already holds scheduled 20 ms visits. Ordinary GLRT uses every sample from both receivers in each valid visit. At 10 MS/s, one visit contains 200,000 sample times and 1.6 MB of interleaved little-endian CI16. The native preparation loop visits both receiver values at every sample. [Native CI16 preparation](../../../../native/adaptive/detector/kernel/private/dwell_input.h) · [Qualification protocol](PROTOCOL.md)

## Available and detector-consumed support

Sample-counter span includes tune and guard gaps with no saved IQ member. The 106 compressed members in each archive contain scheduled dwell bytes. DS29-0082 has 1,904 captures excluded by the original retune and sample-support policy. Both readers still decompress and authenticate their payload bytes, and the detector receives zero invalid visits. GB below uses decimal units.

| Recording | Device span (s) | Scheduled visits / s | Detector visits / s | Stored CI16 (GB) | CI16 presented to GLRT (GB) | Compressed payload (GB) |
|---|---:|---:|---:|---:|---:|---:|
| DS26-0036 | 299.996 | 6,769 / 135.38 | 6,765 / 135.30 | 10.8304 | 10.8240 | 8.1566 |
| DS29-0082 | 300.018 | 6,772 / 135.44 | 4,868 / 97.36 | 10.8352 | 7.7888 | 8.4048 |

A window offset in the index addresses decompressed bytes. The existing members hold continuous Zstandard frames across adjacent windows, and the sealed reader checks each window and both chunk digests. The tested simplification therefore streams the same bytes. It avoids materializing the entire compressed member and keeps the original capture eligibility and GLRT candidate logic. Users selecting a subrange still pay for verification of every overlapping compressed member under this contract.

## Implementation and authority

The installed reader previously collected chunks into byte buffers, joined them, and then passed the whole authenticated compressed byte string to Zstandard. This prototype reads at most 131,072 compressed bytes per call and hashes each block as the decoder consumes it. The stock manifest and index contracts, raw window and raw chunk digests, and compressed member size, identity and digest checks remain in force. Each window's raw digest is checked before it reaches GLRT. Native factors become eligible for positioning only after both raw worker terminal receipts and all segment and global visit checks pass.

The first launcher tried to import the host position stack in the installed archive interpreter. It failed before reading IQ because that interpreter lacks SciPy. The frozen measured worker uses only producer dependencies and delegates numerical positioning back to the host. [Initial launcher source lock](bootstrap-source-lock.json) · [Measured source lock](source-lock.json)

## Memory and timing

The reader-only probes used fresh processes on CPU 1 and the largest sealed compressed member from each recording. Each member held 64 visits. On DS26-0036, peak RSS fell from 259,972 to 113,276 KiB while reading the same 77,366,126 bytes. On DS29-0082 it fell from 265,280 to 114,176 KiB for 79,616,072 bytes. The bounded probe followed the stock probe, which left the member in the filesystem cache. These probes establish resident memory and matching decoded output. Their wall times include different cache states. [Reader-only receipts](reader-probe.json)

| Recording | Raw workers peak RSS, each (KiB) | Storage-attributed reads (GB) | Raw two-lane wall / CPU (s) | Whole wall / CPU (s) | Whole wall s per recorded s |
|---|---:|---:|---:|---:|---:|
| DS26-0036 | 179,416 / 179,268 | 8.894 | 180.16 / 220.55 | 263.32 / 271.90 | 0.878 |
| DS29-0082 | 182,628 / 184,072 | 8.497 | 98.46 / 153.44 | 139.17 / 190.95 | 0.464 |

Storage-attributed reads sum Linux process `read_bytes` for the raw workers and can include read-ahead and other file traffic. The reader returned exactly 8.1566 and 8.4048 GB of compressed IQ, plus 18.24 and 18.41 MB of verified indexes. The full replays use CPUs 1 and 23 for alternating archived segments and CPU 1 for the fit. Fit envelopes were 82.05 and 39.73 s wall. The earlier ordinary runs took 134.82 and 111.86 s through their fixes, on different pins and under different shared host load. The current measured reduction is in memory. [Whole-chain receipts](stage-receipts.json) · [Earlier ordinary complete runs](../../end-to-end/README.md)

The native detector calls used 184.70 and 120.27 aggregate CPU seconds, averaging 27.3 and 24.7 ms per valid visit under these pins. The two-lane raw wall envelope equals 0.601 and 0.328 seconds per recorded second. The archive clocks batch independent segments and include compressed verification, while a live input arrives in chronological dwell order and has its own retune and delivery deadlines. The averages describe the replay host.

## Detector, graph and position parity

Both complete native files matched the prior ordinary SHA-256. DS26-0036 matched 15,073 passing and 44,549 rejected factors, 189 empty probes and four excluded visits. DS29-0082 matched 7,962 passing and 35,413 rejected factors, 68 empty probes and 1,904 excluded visits. The graph audit rebuilt the anonymous tracks independently from each factor file and matched their timing, channel, receiver and frequency arrays, plus support and clock receipts. DS26-0036 kept 104 tracks with 3,610 selected observations. DS29-0082 kept 70 tracks with 2,044 selected observations. [Factor classes](stage-receipts.json) · [Graph parity receipts](graph-receipts.json)

Both calibration-arm endpoints and conditional RMS values were identical to the earlier ordinary fit. With `c = 0` and fitted `c`, respectively, geographic errors were 0.218 / 0.180 km on DS26-0036 and 2.789 / 2.654 km on DS29-0082. Conditional RMS changed from 102.253 to 102.289 Hz and from 106.672 to 106.588 Hz, respectively. The score sheet also includes the four original capture-era v5 geographic references. [Both calibration arms and original references](scores.csv)

## Reproduce

Run against the original read-only recording inventory with the installed producer runtime. The complete replay is sequential between recordings, with two raw workers per case and a compact secant fit. The optional footprint probe reads just the largest compressed member in each archive in both readers. Publication compares the completed products before the separate geographic score read.

```bash
for recording in DS26-0036 DS29-0082; do
  env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    taskset -c 1,23 .venv/bin/python -B -m tools.pipeline_eval.qualification.raw_stream_trial \
    run "$recording" --work /tmp/bounded-raw-stream || break
done
.venv/bin/python -B -m tools.pipeline_eval.qualification.raw_stream_results probe \
  --out /tmp/bounded-raw-report
.venv/bin/python -B -m tools.pipeline_eval.qualification.raw_stream_results publish \
  --work /tmp/bounded-raw-stream --out /tmp/bounded-raw-report
.venv/bin/python -B -m tools.pipeline_eval.qualification.raw_stream_results score \
  --out /tmp/bounded-raw-report
```
