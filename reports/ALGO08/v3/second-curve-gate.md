# Why the second curved screen loses installed mixed-packet support

On the exact DS30-0220 mixed receiver packet, the charted second screen drops **139 installed-only observations** because four candidate curves fail the original conditional slope test and the separate profiled noise test. A fifth curve's **17 observations** pass every individual check and are dropped by the original family support closure. The healthy DS30-0086 control also loses **38 installed-only observations** on a curve with the same conditional slope-only failure and a separate profiled noise failure. These results argue against removing the slope check. [Frozen stage experiment](second-curve-gate-protocol.md) · [Prior exact owner replay](pre-screen-owner.md)

## Original second-drop conditions

The installed crossover owner labels enter only after the live charted gate observations seal. Every row below uses all actual retained-bandwidth observations from its recorded curve. The ordinary seed-stage test uses fixed-zero calibration for the shared support proposal. Its row join is identical in the two existing published calibration arms. The conditional gate combines RMS and five noise tests. On the five directly comparable local failures, only its absolute slope statistic exceeded an original conditional limit, **3.0**. Their independently profiled noise tests also failed. The capture exposes the profile-noise result, without its individual subtest values.

| Case and original Graph component | Installed-only observations | Original time span | Conditional absolute slope z | Conditional slope magnitude, Hz/s | Slope normalization, Hz/s | Actual reason |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 0220 RX1/CH1 T006 | 21 | 28.375 s | 3.006 | 19.32 | 6.43 | Conditional slope and profiled noise |
| 0220 RX1/CH3 T005 | 17 | 25.540 s | 2.228 | 20.94 | 9.40 | Family support closure, one remaining lane |
| 0220 RX1/CH5 T004 | 34 | 42.551 s | 3.568 | 13.43 | 3.76 | Conditional slope and profiled noise |
| 0220 RX1/CH6 T004 | 28 | 31.918 s | 3.605 | 20.99 | 5.82 | Conditional slope and profiled noise |
| 0220 RX2/CH8 T000 | 56 | 55.670 s | 3.528 | 5.58 | 1.58 | Conditional slope and profiled noise |
| 0086 RX2/CH5 T000 | 38 | 29.425 s | 3.693 | 8.70 | 2.35 | Conditional slope and profiled noise |

The 0220 RX1/CH1 and RX1/CH3 curves are the two pre-screen lanes of one original NORAD family. The second curve passes profile RMS, bias and noise, conditional residual, alias and visibility. The first curve's initially small slope overage, **0.00587** in z, removes the other lane and triggers the second deletion. Four other 0220 screen failures account for 244 points without the installed-only owner roles. Their local reasons include step changes in three curves and a larger mean, RMS and slope failure with profile bias and RMS failures in the fourth. The one other 0086 screen loss contains 33 points without the installed-only roles and fails three conditional noise tests, slope, quadratic gain and step. The later paired repair removals of 23 points on 0220 and 29 on 0086 remain outside the measured stage.

The release computes the slope statistic from the absolute residual-time inner product. The receipt has a signed residual mean and RMS but no residual vector or signed slope. It preserves the exact sample-counter spans. In the table, the slope normalization is the original residual scale divided by the square root of the sum of squared centered times. The residual scale comes from the recorded mean, RMS and count, with the original 75 Hz floor. Multiplying by the original unsigned z recovers a magnitude. This scale is part of the detector's test, with no claim that it is a calibrated standard error. Three RX1 0220 local failures have **5.85 s** of overlapping time support across channels. Matching signed drift across those curves or retained peers remains untested, and the evidence cannot identify a shared oscillator correction.

## Custody, exact masks and timed stop

Each source-only preflight bound the existing 50 resident causal snapshots, the exact original mixed packet and offer, all 39 charted logical source hashes, and the actual positive ports. Neither preflight made a position solver call. The worker used that same archive and a single authenticated saved handoff. The instrumented source adds observations of the exact tested conjunctions and records an explicit family closure at the line that rejects its row. A source-bound stop follows the second drop. The named fallback and paired finishing fit are guarded, and no terminal, grid or PNG was generated.

| Case | First gate input / output | Second gate input / output | Saved worker wall / CPU | Paid preamble inside worker wall / CPU | Later official poll after exit |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0220 | 2,253 / 1,731 | 2,209 / 1,809 | 9.340 / 8.727 s | 1.839 / 1.324 s | 22.711 s |
| DS30-0086 | 2,033 / 1,871 | 1,990 / 1,919 | 9.252 / 8.621 s | 1.884 / 1.333 s | 22.797 s |

The four input/output masks independently reproduce the ordered Graph memberships and the earlier observation/NORAD/conditional-role digests in each case. Both processes exited zero under separate nonblocking shared leases, CPU 2, nice 15, idle I/O and one numerical thread. They started 84.5 and 84.0 ms after different authenticated official storage deferrals. The next official polls reported ordinary storage deferral after both children had exited. Resident archive state matched before and after. There were no waveform or backing reads, replayed numerical attempts or final position fits. The timing measures this diagnostic only. Reconstructing all gate decisions from just the old saved curve book would have omitted the shared masked conditional-state work.

The successful children used `ff9f90fec`. Final code independently checks the official event filename timestamp as well as the already checked event body, and no child was repeated for that change. Six component tests passed. The [machine receipt](measurements/second-curve-gate.json.gz), SHA-256 `6eb9e46220096e695eaddfb5b4b0a673d8a28d13035e7caf8a26b9fc5f7df995`, contains both actual ordered gate tapes and their reason checks, original counter spans, source-only checks and official lease evidence. [Stage runner](second_curve_gate_trial.py) · [Read-only grader](second_curve_gate_grade.py)
