# Unchanged whole-track bridge on 24 reserved roof recordings

The bridge published both calibration arms for **20 of 24** reserved recordings. Archived compact secant and all four original v5 options published every recording. The bridge met the paired 10% geographic gate in both arms on **8 of 24** against compact secant and **9 of 24** against original no-repair v5. Its largest new regression was DS26-0068, where fitted-c error rose from 0.296 km with compact secant to 8.452 km. [Two-arm chart](charts/index.html) · [Compact score table](summary.csv)

The reserve includes 21 hash-selected DS26 recordings and all three remaining DS29 recordings. The bridge code and scientific dependencies matched the earlier sealed study byte for byte. Each paired case uses the same stored native GLRT, causal catalogue and original supplied roof tile. The canonical compact archive and all four original options were authenticated before replay. All 24 attempts completed accounting 614.44 seconds after the shared lock. [Protocol](PROTOCOL.md) · [Input and source lock](source-lock.json) · [Prediction and timing receipt](receipt.json)

Each paired table entry gives c0 first and fitted c second. Percentiles describe published fixes. The threshold counts use all 24 scheduled recordings.

| Receiver | Fixes | Within 1 / 2 / 5 km, c0 | Within 1 / 2 / 5 km, fitted | Median error (km) | P95 error (km) |
|---|---:|---:|---:|---:|---:|
| Unchanged bridge | 20 / 20 | 11 / 15 / 19 | 11 / 15 / 19 | 0.865 / 0.860 | 3.516 / 3.471 |
| Canonical compact secant | 24 / 24 | 13 / 22 / 23 | 13 / 22 / 23 | 0.731 / 0.748 | 2.514 / 2.496 |
| Original no repair | 24 / 24 | 13 / 22 / 23 | 13 / 22 / 23 | 0.775 / 0.807 | 2.502 / 2.494 |
| Original selective gap | 24 / 24 | 13 / 22 / 23 | 13 / 22 / 23 | 0.775 / 0.807 | 2.502 / 2.494 |
| Original one omitted track | 24 / 24 | 13 / 22 / 23 | 13 / 22 / 23 | 0.773 / 0.804 | 2.502 / 2.494 |
| Original two omitted tracks | 24 / 24 | 13 / 22 / 23 | 13 / 22 / 23 | 0.773 / 0.804 | 2.502 / 2.494 |

| Paired bridge accuracy against | Within 5%, c0 / fitted | Within 5%, both arms | Within 10%, c0 / fitted | Within 10%, both arms |
|---|---:|---:|---:|---:|
| Canonical compact secant | 8 / 7 | 7 | 12 / 8 | 8 |
| Original no repair | 9 / 8 | 8 | 13 / 9 | 9 |

All three DS29 recordings published. DS26 published 17 of 21. DS26-0271, DS26-0112 and DS26-0311 reached the 140-second child cutoff and returned no coordinates. Their measured whole-worker walls were 141.33, 140.16 and 140.21 seconds. DS26-0046 failed at 100.10 seconds because the original cavity nomination’s family-excluded calibration phase did not converge. These four outcomes remain in both arms and all decision denominators. [Case-level scores](scores.csv) · [Tail and failure ledger](tails.json)

## Runtime and frequency fit

The 20 successful bridge workers took 55.92–131.11 seconds wall, with median 90.12 seconds wall and 62.88 seconds CPU. Median wall across all attempts was 94.33 seconds. Native preparation took 25.01 seconds at the median, after reading the stored GLRT document. Initial plus conservative work took 9.03 seconds, including 1.85 seconds of reclassification. Family, signed and cavity together took 37.52 seconds at the median. These stage medians come from separate distributions. The bridge performed 701.5 recorded native bound calls and 85 compact projector calls at the median on successful runs. The archive preserves the 23 available native receipts. DS26-0311 timed out without a receipt, so its call count is blank.

The archived compact controls had a median of 137.35 seconds full wall, 62.12 seconds initial plus conservative, and 41.25 seconds family through cavity. These are historical measurements from a different run and operating schedule. The fresh reserve used nice 10 on CPUs 20–23. The new full-worker times were outside the earlier 10–30 second target. [Per-stage timing and calls](timings.csv) · [Raw native receipts and digests](native-receipts.jsonl.gz)

Bridge median conditional RMS was 75.79 Hz at c0 and 75.62 Hz with fitted c across its published fixes. Compact medians were 74.91 and 74.74 Hz across its 24 fixes. These RMS distributions describe the retained data of each method. The paired geographic scores use independent receiver coordinates. [Geographic and RF distributions](summary.json)

## Largest regression

The audit selected the largest increase in geographic error against compact secant after the prediction seal. DS26-0068 returned 8.444 km at c0 and 8.452 km with fitted c, against 0.446 and 0.296 km from compact. The divergence was already present in the provisional fit. The bridge warm coordinate reached the 12.5 km east edge of the supplied tile and lay 9.45 km from the original selected c0 initial coordinate in the tile’s east–north plane. It was the only completed bridge run whose warm coordinate hit the tile edge. Two other material regressions, DS26-0253 and DS26-0205, had interior warm coordinates.

The bridge and original cavity checkpoints shared 20 curved tracks in both arms. The bridge omitted 16 original tracks, retained 10 alternative tracks, and used a different owner on one shared 60-point component. Total curved support was 1,123 bridge points against 1,332 original. The bridge had proposed reassignment to original owner 63327 on a separate 14-point curve during the early pass. The shared 60-point curve still had bridge owner 66168 at the cavity boundary. The bridge’s conditional RMS on this recording was about 66.6 Hz in both arms, below compact’s 74.0 and 73.7 Hz. Its retained RF fit did not expose the geographic error. [Matched ownership audit](regression-audit.json) · [Audit receipt](regression-audit-receipt.json)
