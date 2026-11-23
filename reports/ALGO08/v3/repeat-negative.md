# Sparse repeat correlation loses signed lanes before detection

The frozen gate missed **11 primaries and 10 secondaries** on the original 20 ms receiver and **13 primaries** on the active 20/12 ms schedule. Its cost was **24.56 µs per exposed full lane** and **20.44 µs per short lane**. Even a threshold chosen after scoring to retain every signed factor could skip only **2 of 37** empty lanes on the full receiver and **0 of 41** on the mixed receiver. The held physical member stops this feature before receiver integration or localization. [Protocol](repeat-negative-protocol.md) · [Signed decisions and paired clocks](measurements/repeat-negative-held.json.gz)

## Fixed waveform test

Each radio uses its own unprocessed CI16. The score is the largest positive excess of local normalized squared complex coherence at a delay of **40,000 samples** over either control at 39,939 and 40,061. Three frames have exactly 40,000 native samples. Coherence uses centered covariance and its magnitude removes a constant phase between the two tiles. The two controls suppress the response of a stationary tone that repeats similarly at all three delays. Each elapsed block checks twelve phases with 64 stride-four sample pairs. Two separated blocks cover early and late portions of each aperture and the maximum preserves a localized repeat instead of averaging it away. The short call reads only its own prefix. The gate has no frequency estimate, timing proposal, prior, position, antenna sharing or FFT. [Native kernel](repeat_negative.c)

The predeclared cutoff **0.0285717990** comes from 48 deterministic control comparisons over both pilot edges, radios and apertures. The 28 native-positive injected cases and one native-positive tone/noise case all pass. The latter fixes the minimum. An anchor, score tie or invalid score calls the original receiver. The existing one-in-eight per-channel/tuned-RF cadence gives eight stereo anchor visits on this member. Every anchor is paid in both arms. The earlier occupancy study used the median over adjacent rounded frame pairs. Its repetition feature skipped zero of 110 empty lanes at zero observed loss. The earlier cyclic comb used signed spectral shape. [Independent calibration and receipt](repeat-negative-calibration.md) · [Earlier occupancy test](occupancy.md) · [Cyclic shape](cyclic-presence.md)

## Held signed receiver work

DS30-0169 member zero gave 51 admitted and 13 excluded visits. Each aperture's replay preserves the original ordered signed tuple bytes on every call that runs. There are 16 full anchor lanes and 86 opportunities for gating in each comparison. An empty lane means that the matched original detector emitted no tuple. It makes no assertion about whether a physical signal was present. Native rank 0 is primary and rank 1 is secondary.

| Reference and radio | Exposed positive / empty lanes | Empty lanes skipped | Primaries missed | Secondaries missed | Originally selected tuples on missed lanes |
|---|---:|---:|---:|---:|---:|
| Full RX0 | 29 / 14 | 6 | 4 | 4 | 1 |
| Full RX1 | 20 / 23 | 5 | 7 | 6 | 4 |
| Full pooled | 49 / 37 | 11 | 11 | 10 | 5 |
| Mixed RX0 | 27 / 16 | 7 | 6 | 0 | 6 |
| Mixed RX1 | 18 / 25 | 5 | 7 | 0 | 7 |
| Mixed pooled | 45 / 41 | 12 | 13 | 0 | 13 |

The full reference emitted 110 tuples, including 50 secondaries. The mixed reference emitted 66, including ten secondaries on its protected anchors. All 13 missed mixed tuples had passed the original short verifier and were selected for publication. Full misses include both signed intervals and factors with a wide range of correlation margins. Some missed full factors had still been available to later continuation even when the old output did not select them. The last table column counts presented tuples on the omitted lanes directly from the sealed reference packet. It does not price downstream continuation changes. [Original signed aperture comparison](receiver-ceiling-0169.md)

| Reference | Original detector CPU / elapsed, ms | Routed CPU / elapsed, ms | Total gate CPU, ms | Native CPU removed from genuine empty lanes, ms | Free perfect empty referee, native CPU saved, ms |
|---|---:|---:|---:|---:|---:|
| Full | 284.452 / 284.485 | 228.130 / 228.152 | 2.112 | 13.754 | 44.310 |
| Mixed | 135.216 / 135.227 | 111.035 / 111.037 | 1.758 | 9.953 | 32.861 |

The routed clocks include the gate and every paid stock call in two rotated comparisons over the same decoded member. They save time in part by throwing away verified evidence. At the descriptive zero-loss cutoffs of **0.01365088** (full) and **0.01332108** (mixed), the full gate could save at most **2.486 ms** of measured native CPU before paying **2.112 ms** for features. Mixed would pay **1.758 ms** and save no native calls. The full zero-loss remainder is roughly **0.37 ms** before additional overhead. This held result gives no basis for a useful, transferable negative gate from this statistic, despite its cheap native evaluation. The study does not address classifiers with different waveform information. No localization or RF comparison ran.

## Signed intake and reproducibility

Intake read the staged tmpfs index and one compressed payload. Its **19,252 of 19,252** pages were resident, and the read accounted for **zero storage input blocks**. The reader verified the staging manifest, both member digests, decoded payload and all 64 original I/Q digests. Intake and authentication took **229.594 CPU / 229.618 elapsed ms** once outside both detector clocks. All 102 admitted lanes joined the sealed ordered traces for both original apertures. No original archive, unconditioned input or second member opened. [Driver](repeat_negative.py)

Run the two commands under the existing one-CPU Gauss lock with the staged receiver's capture account, `TMPDIR=/dev/shm`, nice 15, best-effort I/O priority 7 and one numerical thread. Use `-BP -m reports.ALGO08.v3.repeat_negative calibrate CALIBRATION_TMPFS_DIR` first. Record the raw calibration file SHA-256 before running `-BP -m reports.ALGO08.v3.repeat_negative validate HELD_TMPFS_DIR CALIBRATION_TMPFS_DIR/calibration.json CALIBRATION_SHA256`. The uncompressed held receipt SHA-256 is `abcd7820f6e883021331e0ae1edc3bc2102f9c87e44182187c099ce2cddd35df`. Four tests passed, covering exact lag and stereo isolation, a stationary tone, aperture confinement, anchor and invalid-input fallback, and secondary-factor accounting. [Tests](../../../tests/pipeline_eval/test_repeat_negative.py)
