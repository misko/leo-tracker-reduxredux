# Native detector queues at the recorded arrival cadence

Each raw window spans 20 ms. Host delivery gaps had medians of **43.54 ms on DS26-0197 and 43.45 ms on DS29-0316**. Their 95th percentiles were 49.19 and 49.11 ms. The complete delivery spans were 299.978 s and 299.986 s, covering 6,772 and 6,774 physical visits. The first recording has 11 original hardware exclusions. The second has none. The queue admission denominator is therefore 6,761 and 6,774 valid visits per method. [Stage chart](queue-evidence.png) · [Locked protocol](PROTOCOL.md)

## Actual paced replay

All four complete runs returned. One waiting slot dropped 8 and 16 valid visits for stock, and 40 and 55 for fifth-center. Stock emitted about **92%** of retained packets before the next physical delivery. Fifth-center emitted **55% and 53%** by that boundary. The denominator for a following delivery excludes the recording's last visit. Queue drops remain separate.

| Recording | Detector | Emitted / valid | Schedule to emission p50 / p95 / max | Max queue wait | After final delivery |
|---|---|---:|---:|---:|---:|
| DS26-0197 | Stock | 6,753 / 6,761 | 31.71 / 50.80 / 213.73 ms | 136.03 ms | 25.53 ms |
| DS26-0197 | Fifth center | 6,721 / 6,761 | 43.29 / 72.31 / 166.73 ms | 109.16 ms | 38.96 ms |
| DS29-0316 | Stock | 6,758 / 6,774 | 31.80 / 51.19 / 186.38 ms | 111.17 ms | 23.59 ms |
| DS29-0316 | Fifth center | 6,719 / 6,774 | 43.75 / 74.53 / 155.80 ms | 109.45 ms | 35.76 ms |

Packet age starts at the scheduled recorded delivery and ends at verified native emission. Queue wait starts at actual dispatch and ends at detector entry. All inputs were decoded before their scheduled arrival. Actual dispatcher wakeups were sometimes late, with maxima from 34.9 to 104.5 ms. All 26,951 emitted native visit envelopes match their prior complete native bytes by canonical SHA-256. All four services completed between 300.74 and 300.87 s. Charged memory reached 512 MiB. Process RSS peaks were approximately 207–221 MiB, without swap or OOM. [Paced measurements](paced-replay.csv) · [Per-visit clock and sample-counter trace](paced-events.json.gz) · [Actual drops](observed-drops.csv)

## Position after the actual queue drops

The same phase-release receiver fitted every retained input and issued four fixes per calibration arm. Each retained fit uses only the two-receiver packets that actually emitted, reconstructed from the byte-verified originals, with the original capture clocks, causal archive and 25 km offer. All pairs below are `c = 0` / fitted `c`.

| Recording | Detector | Dropped visits | Full unpaced error → paced-retained error | Full unpaced RF RMS → paced-retained RF RMS |
|---|---|---:|---:|---:|
| DS26-0197 | Stock | 8 | 0.792 / 0.992 → 0.784 / 0.989 km | 80.516 / 80.556 → 80.456 / 80.497 Hz |
| DS26-0197 | Fifth center | 40 | 0.759 / 0.937 → 0.807 / 0.988 km | 83.485 / 83.501 → 83.559 / 83.571 Hz |
| DS29-0316 | Stock | 16 | 0.834 / 0.852 → 0.715 / 0.718 km | 119.815 / 119.818 → 121.344 / 121.349 Hz |
| DS29-0316 | Fifth center | 55 | 0.218 / 0.218 → 0.725 / 0.682 km | 120.068 / 120.063 → 122.289 / 122.302 Hz |

Dropping 55 of 6,774 valid DS29-0316 visits moved the fifth-center endpoints 788/753 m. It erased most of that recording’s earlier fifth-center position advantage. Paced stock on DS29-0316 had lower position error and higher RF RMS than full stock. This is the measured effect of one hardware-clock replay with one waiting slot on two recordings. Retained solver wall times were 74.8–89.4 s and were measured after capture as separate factor-to-position runs. The paced packet-age metric excludes this solve. [Position and RF CSV](position-scores.csv) · [Both calibration chart sets](position-charts/README.md) · [Position evidence seal](position-score-lock.json)

## Finite queue model from earlier complete calls

The model feeds the full published stock, fifth-center and incremental visit clock series into one- and two-worker FIFO schedules. It separately uses each earlier native call’s thread/process CPU or wall interval. The table shows the one-worker wall version. The CPU version predicts zero drops for every one-slot row. It predicts 0/1, 1/2 and 629/843 zero-slot drops for stock, fifth and incremental across the two recordings, respectively. A slot counts one waiting packet in addition to the worker's running packet.

| Recording | Native path | Zero-slot drops | One-slot drops | Minimum lossless waiting slots | Maximum age, lossless |
|---|---|---:|---:|---:|---:|
| DS26-0197 | Stock | 19 | 7 | 9 | 434 ms |
| DS26-0197 | Fifth center | 152 | 76 | 23 | 1,049 ms |
| DS26-0197 | Incremental | 847 | 38 | 10 | 484 ms |
| DS29-0316 | Stock | 10 | 0 | 1 | 89 ms |
| DS29-0316 | Fifth center | 185 | 113 | 62 | 2,777 ms |
| DS29-0316 | Incremental | 951 | 31 | 5 | 250 ms |

Modeled wall service includes descheduling on the earlier unpaced launches. Those launches used different core pairs for incremental and the other modes. The wall model can overstate slow bursts after changing workload and core layout. The CPU model excludes such stalls. Both are exact finite-queue calculations on the supplied intervals. With two modeled wall-time workers and one waiting slot, stock dropped 1/0, fifth dropped 7/18, and incremental dropped 1/0 across the two recordings. No two-worker paced implementation was run. [All modeled queues](queue-model.csv) · [Modeled drop counter ledger](modeled-drops.json.gz)

## Matched-core native cost

The fixed midpoint block uses visits 3322–3449 on DS26 and 3323–3450 on DS29. Each block contains 128 consecutive native opportunities selected by visit index alone. Each detector ran on the same bytes and physical core as the two other detectors for that recording. The order rotated by visit after one warm call per method. All 768 measured native envelopes match the corresponding sealed whole-recording result. The table uses thread CPU from the same complete detector call boundary, including the scout and decoding the native output.

| Recording and CPU | Stock median | Fifth median | Incremental median |
|---|---:|---:|---:|
| DS26-0197 · CPU20 | 24.77 ms | 31.65 ms | 35.85 ms |
| DS29-0316 · CPU21 | 24.60 ms | 31.39 ms | 38.38 ms |

These representative block results complement the earlier six-window matched control stratified by the count of stock-positive lanes. They measure detector work without paced admission or position solving. [Native cost and tails](same-core-summary.csv) · [Measured individual calls](same-core-visits.json.gz) · [Earlier matched control](../whole-incremental-rescue/paired-host-detector.csv)

## Physical scope and reproducibility

The paced CPU18 and CPU19 runs each used one detector, one waiting slot with newest-drop overload handling and an independent eight-window decoder prefetch. The decoder, pace dispatcher and detector shared the assigned case core. Each systemd service enforced 512 MiB charged memory, zero swap and a 350 s wall cap. Raw physical clocks and native sample counters came from the saved retune receipts. Each emitted visit envelope was checked against its corresponding whole-IQ archive. The raw source included all scheduled samples even when its valid visit was rejected by the detector queue. Dropped valid packets never count as original hardware invalidity. [Source and input lock](source-lock.json) · [Stage receipts and plot seal](stage-lock.json)

The first launcher attempts stopped before the initial prefetch because the service account could not read the protected capture manifests. The retry uses the same read-only archive account as the published IQ replays and gives that worker scoped access to local scratch. No policy, source roster, clock, cap or fitted model changed. [Initial terminal receipts](preflight)
