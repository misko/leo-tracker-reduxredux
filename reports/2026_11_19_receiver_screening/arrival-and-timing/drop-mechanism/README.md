# Position sensitivity after a small number of missing visits

The three attachments on the real DS29-0316 loss shifted either calibrated position by less than 9 m and left most of the original 753–788 m displacement intact. The same rule helped DS26-0197 on the independent count-matched pattern. The trials show a position sensitivity to how the surviving observations enter the model, even when latent satellite identities remain stable.

The complete and queue-retained fifth-center runs on DS26-0197 and DS29-0316 differ by 40 and 55 measured two-receiver omissions. Packet hashes bind the source and retained outputs. These omissions contain 35 and 48 gated winners, respectively. The remaining probe packets retain their original measurement candidates. As a separate control, the same number of valid visits was removed by a fixed recording-and-visit hash independent of detector outputs and location. [Frozen inputs and visit sets](plan.json) · [Protocol](PROTOCOL.md)

The original Graph preview rules out two simple breakpoints. None of the complete tracks crossed the configured 10 s continuity limit solely because of omitted observations. The complete positive lanes had at most 17 and 24 predecessors within the window, below the Graph's 48-neighbor cap. Instead, DS29-0316 changed group membership on a much larger scale than DS26-0197. Sixteen complete groups split on DS29-0316 and sixteen retained groups merged points from multiple complete groups. Twenty-seven surviving points that belonged to complete groups became unassigned, while 32 previously unassigned points joined groups.

The tested repair can join an observed unassigned positive to a retained same-lane track when known missing-visit timing lies inside the relevant bracket. It requires one unique polynomial owner within the stock 450 Hz ambiguity gate and a residual within one configured noise sigma, 150 Hz. It preserves existing owners and curvature classes and uses the detected CFO of each joined point. The existing compact receiver then runs on those groups with its original signed and cavity logic. [Repair source](../../../../tools/pipeline_eval/variants/drop_reconnect.py)

## How the untreated loss changes the fit

On DS29-0316, the actual drop removed 27 active curved observations directly. Another 136 delivered points from the complete final curved support stopped contributing, and 335 other delivered points entered the curved fit. All 2,420 shared final curved points kept their assigned NORAD, as did all 2,624 shared active points at the preceding conservative stage. The final model changed from a fit with 602 predictive-linear points to a curved-only fallback. Neither solve offered cavity recovery.

The count-matched DS29-0316 input omitted 43 gated winners, retained predictive-linear fitting, and used 771 such points. Its endpoints still moved 588 m at zero c and 582 m at fitted c relative to complete, compared with 788 m and 753 m from the actual omissions. It split 17 complete groups and merged parts of complete groups in 18 retained groups. The continued position sensitivity with predictive-linear fitting shows that the actual fallback is only one part of the mechanism.

DS26-0197 lost 25 complete final active curved observations directly. Every surviving complete final active curved point remained active, and the complete and real-drop fits both used the signed-event path. The independent count-matched input removed 29 gated winners and its fitted positions moved 226 m and 210 m. It finished with no predictive-linear points. Equal visit counts produced different support and position changes in both recordings. [Point, group and path differences](path-effects.json)

## Position after the reconnect

| Recording | Input | Gated winners removed | Reattached | Horizontal error | Conditional Doppler RMS |
| --- | --- | ---: | ---: | ---: | ---: |
| DS26-0197 | Complete | 0 | 0 | 0.759 / 0.937 km | 83.485 / 83.501 Hz |
| DS26-0197 | Real loss | 35 | 0 | 0.807 / 0.988 km | 83.559 / 83.571 Hz |
| DS26-0197 | Real loss, corrected | 35 | 0 | 0.807 / 0.988 km | 83.559 / 83.571 Hz |
| DS26-0197 | Hash loss | 29 | 0 | 0.968 / 1.121 km | 85.318 / 85.329 Hz |
| DS26-0197 | Hash loss, corrected | 29 | 10 | 0.889 / 1.072 km | 85.222 / 85.230 Hz |
| DS29-0316 | Complete | 0 | 0 | 0.218 / 0.218 km | 120.068 / 120.063 Hz |
| DS29-0316 | Real loss | 48 | 0 | 0.725 / 0.682 km | 122.289 / 122.302 Hz |
| DS29-0316 | Real loss, corrected | 48 | 3 | 0.728 / 0.685 km | 122.249 / 122.262 Hz |
| DS29-0316 | Hash loss | 43 | 0 | 0.497 / 0.491 km | 121.351 / 121.348 Hz |
| DS29-0316 | Hash loss, corrected | 43 | 0 | 0.497 / 0.491 km | 121.351 / 121.348 Hz |

Each pair lists zero c and fitted c. The zero-attachment replays reproduced their corresponding untreated scientific outputs exactly. The three DS29-0316 real-drop links included one previously grouped point from the complete run. The fit still used the curved-only fallback. Conditional RMS improved by about 0.04 Hz in each arm, while geographic error increased by about 3 m. On DS26-0197, the ten hash-drop links included one previously grouped point and restored acceptance of a 487-point predictive-linear set. The error fell by 78 m and 49 m. Both corrected hash errors remained above the complete-recording errors. [Both-arm scores, objectives and original v5 references](scores.csv) · [Real and hash position charts](figures.json)

Ten fresh factor-to-position services completed on the two assigned cores under 512 MiB cgroups with zero swap. All complete and genuine retained endpoints and counters exactly reproduced their sealed parents. Service wall ranged from 95.3 to 136.3 s and peak cgroup memory from 286.2 to 384.0 MiB. The times start at stored detector factors and include the instrumented receiver. [Measured runtime and stages](resources.csv) · [Prediction lock](prediction-lock.json)
