# Frozen-method held acquisition transfer

All twelve held recordings complete: 288 paired windows, 576 distinct native
receiver-window owners, no failed or substituted cells. The independent audit
passes native ownership, earlier-only forecasts, R01 selection/confirmation
receipts and separate R02 decisions. There is a held timing/detection transfer;
independent frequency precision, satellite identity and localization improvement
remain unestablished. No graph or position analysis is performed here.

| Method | Pilot passes | Continuity admissions | New original-negative owners | Original reconfirmed | Lost if replaced |
|---|---:|---:|---:|---:|---:|
| R01 point | 83 | 77 | 3 | 74 | 136 |
| R01 search | 222 | 209 | 23 | 186 | 24 |
| R02 consistent linear | 72 | 67 | 4 | 63 | 147 |
| R02 quadratic/fallback | 161 | 157 | 7 | 150 | 60 |
| R02 descriptive legacy | 67 | 59 | 4 | 55 | 155 |

Original acquisition has 210 detections. Every original is retained under the
additions-only policy: loss is zero. The last column diagnoses a replacement
policy that is not used. Adding R01 search admissions would give 233/576 owners;
the separate R02 method would give 217/576. These are research application
counts, not a production change or a target-wise union of methods.

R02 gains 90 admissions and loses none against its matched full-window
consistent-linear control. CH5–8 gains 60 and loses none, from 45 to 105
admissions. The 205 fallback cells have identical consistent-method decisions;
249 cells qualify for the sealed quadratic, and 122 remain without donors.
No held outcome alters a branch, rate, width, timing point or acceptance rule.

| Channel | Cells | Original | R01 pilot / admitted / new | R02 quadratic pilot / admitted / new |
|---|---:|---:|---:|---:|
| CH1 | 96 | 40 | 44 / 42 / 5 | 33 / 33 / 1 |
| CH4 | 96 | 28 | 29 / 28 / 3 | 20 / 19 / 0 |
| CH5 | 96 | 43 | 44 / 39 / 2 | 36 / 36 / 0 |
| CH6 | 96 | 34 | 36 / 35 / 4 | 26 / 25 / 2 |
| CH7 | 96 | 29 | 31 / 29 / 4 | 23 / 22 / 3 |
| CH8 | 96 | 36 | 38 / 36 / 5 | 23 / 22 / 1 |
| CH5–8 | 384 | 142 | 149 / 139 / 15 | 108 / 105 / 6 |

On CH5–8, additions-only counts are 157/384 for R01 and 148/384 for R02,
versus 142/384 original. Held baseline density differs from development's
69/384, so the change in added counts is not by itself a transfer degradation
rate. Shared histories and nearby channel/receiver visits are dependent.

| Recording | Original | R01 search admitted / new | R02 quadratic admitted / new |
|---|---:|---:|---:|
| DS24-0015 | 18 | 17 / 1 | 18 / 2 |
| DS24-0016 | 26 | 27 / 1 | 20 / 1 |
| DS24-0019 | 13 | 13 / 1 | 11 / 0 |
| DS24-0075 | 11 | 13 / 2 | 10 / 0 |
| DS24-0077 | 19 | 19 / 1 | 16 / 0 |
| DS24-0081 | 14 | 14 / 3 | 6 / 1 |
| DS24-0083 | 14 | 15 / 1 | 9 / 0 |
| DS24-0085 | 20 | 19 / 2 | 14 / 1 |
| DS24-0089 | 20 | 11 / 2 | 6 / 0 |
| DS24-0091 | 22 | 22 / 3 | 16 / 0 |
| DS24-0093 | 21 | 25 / 4 | 19 / 2 |
| DS24-0095 | 12 | 14 / 2 | 12 / 0 |

`summary.json` provides all five methods' pilot, compatibility, admission,
retention and frequency counts for every recording/channel/native-RX cell.
`cells.csv` retains individual decisions. Native RX0/RX1 mean display RX1/RX2.

R01's 23 new admissions include 18 nonzero frequency innovations; 12 of the
15 new CH5–8 admissions have nonzero innovations. Fourteen new R01 admissions
use one donor, four use two, four use three and one uses five. Sparse histories
therefore remain central to recovery. Their heuristic CFO intervals can be
broad: the largest new innovation is 16,867.90 Hz. A changed selected bin does
not certify the correct signal identity or independently precise Doppler.

R02 selects the zero residual bin in 150/157 admissions and 5/7 new owners
(4/6 new CH5–8 owners). Its two nonzero new innovations each have magnitude
443.892 Hz. The donor-centered FFT grid and unqualified uncertainty remain.
Zero-bin outputs have later pilot support but numerically copy the earlier
forecast; nonzero outputs also require independent accuracy/identity evidence
before use as precise new frequency information.

![Held additions and frequency innovations](held_comparison_v2.png)

R01 point/search nominate on one subset and confirm on disjoint guarded pilot
frames. R02 scores a predeclared primary point over full-window pilot support.
Their cross-method totals are not a same-support timing ablation; the matched
R02 controls do isolate the frozen timing-policy effect. No companion-method
union or recovered-observation feedback is used. These recordings were held
out from this revision but exposed to earlier studies at the existing site.
This is not new-site validation or deployment false-alarm qualification.

The audit verifies all 576 fresh frozen forecasts and native owners, current
public index hashes, integer hardware generations versus stream labels,
original earlier donor ownership, exact packet/forecast identity, deterministic
R01 ranking and saved selection hashes, disjoint confirmation support, and
every R02 margin/continuity decision. Three owned tests pass. Locked producer
receipts document full public-reader exhaustion; this audit does not reread IQ.
Historical paired-detector parity is global reused evidence, not a fresh blind
acquisition replay on held windows.

Cumulative producer process time is 527.77 s across twelve bounded shards:
68.54 s native read/verification, 300.09 s R01 scoring and 130.10 s R02 scoring.
These are summed process durations, not serial or embedded wall-clock cost.
This audit adds zero IQ reads, scores, algorithm changes or positions.

The raw authorization binds timing protocol
`7bfccde3b823cf48c297ae23f21400ddd21f19b92ba9ed3867d4c5bd00dbf646`.
Audit source protocol:
`168e22bdccdcb5a99d2f2377b96dc866d183c336dc547c54416e309a285a8c87`.
Each completed shard is hash-bound in `source_seals/`; `case_audits/` and
`artifact_seal.json` bind the full readback. The initial unprivileged metadata
hash failure is preserved in `preparation_attempt01.json`. Figure v2 only moves
legends outside data; its source and original figure remain preserved.
