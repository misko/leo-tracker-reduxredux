# Cross-receiver reuse diagnostic from the previous replay

This read-only, post-outcome inspection uses
`../native_tradeoff/results.real.json`, SHA-256
`3241b3f84a800e67650d6af0c9a8c5904ed3ef02467f1b91c9eaabce4d1ace9c`.
It does not run DSP or change the two-candidate protocol.

For each of the eleven application-positive receivers that the original native
detector declared inactive, inspect the native positive pair on the opposite
receiver from the same visit. Compare it with every application pair on the
inactive receiver using the same circular timing and physical-CFO coordinates.
No opposite-receiver pair falls within both the 2 us and 8 kHz association gates
for both pair members. Thus blindly copying the other receiver's measured
timing/CFO is not an evidenced rescue for these eleven misses.

For illustration, choose the reference pair minimizing the sum of maximum
timing error divided by 2 us and maximum CFO error divided by 8 kHz:

| Rate | Visit | Inactive native RX | Maximum timing error | Maximum CFO error |
|---|---:|---:|---:|---:|
| 2.5 MS/s | 1083 | 1 | 0.070 us | 457096 Hz |
| 2.5 MS/s | 1084 | 1 | 291.697 us | 374868 Hz |
| 2.5 MS/s | 1104 | 1 | 0.138 us | 456991 Hz |
| 5 MS/s | 1082 | 0 | 271.459 us | 315030 Hz |
| 5 MS/s | 1085 | 0 | 0.287 us | 457701 Hz |
| 5 MS/s | 1089 | 0 | 259.887 us | 315361 Hz |
| 5 MS/s | 1091 | 0 | 256.385 us | 315687 Hz |
| 5 MS/s | 1093 | 0 | 0.179 us | 457663 Hz |
| 5 MS/s | 1094 | 0 | 0.335 us | 457916 Hz |
| 5 MS/s | 1100 | 0 | 0.079 us | 457745 Hz |
| 5 MS/s | 1107 | 0 | 54.337 us | 457421 Hz |

These differences may involve distinct signals, receiver calibration, or
acquisition aliases; the receipt alone does not establish their physical cause.
Some cases align closely in timing, so a separately evaluated timing-only
proposal followed by an independent full CFO search remains plausible. This
table does not authorize transferring measured CFO or asserting common signal
identity. Existing causal tracking correctly keeps receiver identity in its
cache key and confirms fresh samples on that receiver.
