# Recorded IQ through ordinary GLRT and joint orbit positioning

Two full five-minute archive replays reached their position decisions in **131.16 s** and **109.86 s**. DS26-0036 published a fix in both calibration arms. DS29-0082 withheld both arms on weak held-track support. The candidate validated the complete ordinary factor archive, rebuilt Graph tracks and ran the unchanged joint solver without a v5 position calculation. [Sealed outputs](prediction-lock.json) · [Position comparisons](scores.csv)

## Matched positions

Each pair gives `c = 0` followed by fitted `c`. Errors are kilometres. The archived compact secant control uses the identical ordinary native file and causal catalogue. The archived capture-era joint control uses the same Graph algorithm, backend and tile with the capture-era detector factors. The four original v5 roles are separate geographic references. [All original and matched controls](scores.csv)

| Recording | Ordinary IQ + joint | Ordinary IQ + compact secant | Capture-era factors + joint | Capture-era original no-repair v5 |
|---|---:|---:|---:|---:|
| DS26-0036 | 1.112 / 0.454 | 0.218 / 0.180 | 1.833 / 1.016 | 1.278 / 1.208 |
| DS29-0082 | Withheld / withheld | 2.789 / 2.654 | 1.550 / 1.643 | 0.567 / 0.517 |

On DS26-0036, changing the detector improved the joint solver’s errors by 0.721 and 0.562 km, while conditional Doppler RMS increased from 164.35 / 135.18 to 176.14 / 147.42 Hz. The compact secant solver retained better geographic accuracy from the same ordinary factors. On DS29-0082, the ordinary joint solve lowered conditional RMS from 249.73 / 213.33 to 206.58 / 149.76 Hz and lowered held scores from 0.346 / 0.318 to 0.263 / 0.290. Its forced errors of 2.405 / 1.941 km remain diagnostic. Fitted `c` lowered conditional RMS in both records. It reduced the published DS26-0036 error from 1.112 to 0.454 km and left the DS29-0082 withholding decision in place. [RF and geographic ablation](scores.csv)

The DS26-0036 `r0` omitted-tile query used the same complete native bytes, rebuilt Graph digest and causal catalogue. The worker withheld both arms on weak held-track support in 5.43 s. Forced errors were 24.205 / 24.300 km. The frozen StarLoc and Altrincham alternate-site entries contain no raw recording locators. [Omitted-tile receipt](missing-tile-lock.json)

## Complete input proof

The two installed producer runtimes authenticated every stored visit using the same 128 KiB bounded reader. Assembly checked each lane’s terminal receipt and each segment’s manifest, order, clocks, exclusion and native factor evidence. The newly written native files exactly matched the prior complete ordinary hashes. The numerical worker mounted those files read-only and hashed all their bytes as it streamed the probe array. The bound request contains the actual native and track configuration digests, causal catalogue, cutoff and supplied tile. Both independently computed Graph digests equal the earlier ordinary Graph projections. [Actual worker requests and stage receipts](stage-receipts.json) · [Locked source and input hashes](source-lock.json)

| Recording | Processed visits / excluded | Streamed native bytes | Read probes / winners | Ordinary native SHA-256 prefix | Graph SHA-256 prefix |
|---|---:|---:|---:|---|---|
| DS26-0036 | 6,765 / 4 | 22,518,405 | 13,530 / 3,610 | `41b74326231d` | `38124d94670a` |
| DS29-0082 | 4,868 / 1,904 | 16,908,503 | 9,736 / 2,044 | `9b66406e24a9` | `db378a819642` |

## Whole decision and memory

The whole clock starts before archive preparation and ends at the returned matched-tile decision. Host CPU accounting captures supervisor and waited raw processes. The separate sandbox worker measures its own numerical CPU. The whole CPU column adds the measured sandbox contribution of 3.73 and 2.62 s to the host counters. The two raw lanes can use more CPU seconds than elapsed seconds. The raw and assembly envelope includes authentication, classification and factor output. The separately timed omitted-tile query reuses the fresh factors. [Machine timing receipts](stage-receipts.json)

| Recording | Raw two-lane wall / CPU (s) | Assembly wall (s) | Fit enclosure wall (s) | Graph / joint wall (s) | Whole wall / CPU (s) | Wall s per recorded s |
|---|---:|---:|---:|---:|---:|---:|
| DS26-0036 | 125.27 / 214.30 | 0.86 | 5.01 | 1.59 / 1.56 | 131.16 / 218.89 | 0.437 |
| DS29-0082 | 105.93 / 175.98 | 0.86 | 3.06 | 0.82 / 1.35 | 109.86 / 179.46 | 0.366 |

The supervisor recorded 10.830 / 10.835 GB decoded CI16 and 8.157 / 8.405 GB returned compressed data. Linux attributed 9.641 / 8.552 GB of storage traffic to the raw workers, including read-ahead and other file reads. The host used CPUs 14 and 15 for alternating recorded segments. These elapsed rates describe batch replay. The earlier compact secant runs used other pins and took 134.82 / 111.86 s end to end, with fit enclosures of 44.34 / 36.69 s. The main current whole-chain cost is still the raw acquisition and detector. [Earlier ordinary secant receipts](../../end-to-end/README.md)

The raw workers and the assembly supervisor each had a 768 MiB virtual-address limit. The isolated fitter had a 512 MiB limit. Process RSS sums can count shared pages twice. The near-time summed RSS uses 250 ms sampling with maximum sample separation of 550 ms. The sum of separately observed raw-process peaks is an upper bound on their combined process RSS.

| Recording | Raw max individual RSS / VM (KiB) | Raw sampled concurrent RSS sum (KiB) | Raw sum of individual RSS peaks (KiB) | Assembly RSS / VM (KiB) | Graph + joint RSS / VM (KiB) |
|---|---:|---:|---:|---:|---:|
| DS26-0036 | 179,060 / 363,404 | 357,524 | 357,980 | 259,700 / 450,016 | 143,300 / 383,668 |
| DS29-0082 | 183,268 / 366,608 | 365,032 | 365,704 | 218,988 / 411,284 | 139,912 / 381,756 |

## Reproduce

Use the same sealed read-only recording inventories, installed producer runtimes and [deployed native joint bundle](../../inference/native-joint/README.md). Run each case sequentially with both pins available. The first run also produces the omitted-tile control. [Protocol](PROTOCOL.md)

```bash
for recording in DS26-0036 DS29-0082; do
  env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    taskset -c 14,15 .venv/bin/python -B -m tools.pipeline_eval.qualification.iq_joint_trial \
    run "$recording" --work /tmp/iq-to-joint || break
done
.venv/bin/python -B -m tools.pipeline_eval.qualification.iq_joint_results publish \
  --work /tmp/iq-to-joint --out /tmp/iq-to-joint-report
.venv/bin/python -B -m tools.pipeline_eval.qualification.iq_joint_results score \
  --out /tmp/iq-to-joint-report
```
