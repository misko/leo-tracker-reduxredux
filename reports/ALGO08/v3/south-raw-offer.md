# Same receiver, different operator region on South

The combined candidate **published a false fix** on the signed South offer that excludes the receiver by 100 m. The normal command used the same original 1,200 stereo visits, causal archive, receiver, orbit index and solver as on the containing offer. All 456 ordered factors, their signal and frequency measurements, and the final satellite assignments for both calibration arms matched across offers. The 25 km-wide search square moved 200 m. The fixed-zero position moved **0.66 m** and the fitted position **0.25 m**. [Frozen procedure](south-raw-offer-protocol.md) · [Original-input receipt](measurements/south-raw-omitted.json.gz)

| Original raw replay | Truth relative to nearest face | Error with fixed / fitted calibration | Outcome | Elapsed |
|---|---:|---:|---|---:|
| Containing | 100 m inside | 553.23 / 823.86 m | Fix, eight PNGs | 10.685 s |
| Near omission | 100 m outside | 553.57 / 824.08 m | False fix, eight PNGs | 15.278 s |

On the omitted offer the two estimates sit **313 and 237 m inside** the boundary. Both arms would pass a simple test for an estimate falling on the boundary. The solver made 24 regional probes and stopped the exterior test at its separation check. Both position sidecars bind the new position PNG and use the supplied region. The new matched grid has 137 evaluated points, and all eight figures verified. Historical named v3 and the earlier all-paid receiver also falsely published on this offer. [Containing receipt and earlier comparators](combined-raw-south.md)

| Single-core cost | Containing | Near omission |
|---|---:|---:|
| User CPU | 10.121 s | 10.372 s |
| System CPU | 0.560 s | 4.891 s |
| Authenticated acquisition elapsed | 5.136 s | 8.701 s |
| Decision and publication elapsed | 4.968 s | 6.022 s |
| Minor / major faults across process | 114,169 / 0 | 584,938 / 2 |

All 384,361 waveform and 188 index pages were resident at admission and exit on both runs. The omitted child recorded 40 process-wide input blocks. Most of the elapsed difference coincides with additional system CPU. These are independent launches with a different region, and their clocks do not identify the cause of the system cost. This repeat contributes one geographic control and no additional independent recording to either speed gate. The paired physical positive and the missing-region reliability issue remain open.
