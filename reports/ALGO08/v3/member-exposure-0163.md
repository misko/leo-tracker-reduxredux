# What alternating original members retain on DS30-0163

Keeping even-numbered compressed members in their original order retained **4.186 of 8.356 GB** and **1,858 of 3,731** nonempty receiver opportunities. All 14 original segment manifests matched the SHA-256 values in the frozen acquisition request. The join used the original 20 ms detector outputs and hardware counters. It required approximately 92 kB of manifest files and zero additional waveform bytes.

| Coverage | All members | Even members |
|---|---:|---:|
| Original compressed members | 106 | 53 |
| Issued stereo visits | 6,772 | 3,392 |
| Admitted stereo visits | 5,330 | 2,659 |
| Receiver opportunities | 10,660 | 5,318 |
| Receiver opportunities with detections | 3,731 | 1,858 |
| Largest interval between successive opportunities on one receiver and RF channel | 1.421 s | 5.324 s |

Among the 14 receiver/channel pairs with any detections, the retained share ranged from **47.5% to 51.3%**. The remaining two pairs were empty in the original. The longer gaps matter because a comparable number of observations per channel can still leave different orbital geometry available to the position fit. These are potential skipped bytes. Measuring an end-to-end speedup requires an original-file implementation with its actual integrity checks and publication costs.

[Per-member byte counts and per-stream coverage](measurements/member-exposure-0163.json) · [Measurement implementation](member_exposure_0163.py)
