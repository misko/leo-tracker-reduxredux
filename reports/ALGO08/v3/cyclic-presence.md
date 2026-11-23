# Cyclic comb shape fails to screen empty 12 ms lanes

The fixed screen missed **3 of 21 dense** and **4 of 34 weak** verified 12 ms positives. It skipped **2 of 11 dense** and **0 of 2 weak** empty lanes. Even with a threshold chosen in hindsight to retain every positive on each slice, it could skip only **1 of 11 dense** and **0 of 2 weak** empties. The weak acquisition budget needs **670 of 839** empties at zero screening cost and **749 of 839** at 66 µs per short opportunity. The gap stops this screen before any receiver or localization replay. [Frozen protocol](cyclic-presence-protocol.md) · [Signed decisions and full ROC](measurements/cyclic-presence.json.gz)

## Fixed shape score and observed recalls

The original lag-one comb makes 16,384 disjoint complex products, uses the fixed 16 pilot harmonics and scores the entire signed tuner interval. The gate's sole statistic is `1 - p4/p1`, where `p1` and `p4` are the first and fourth greedy maxima with the original 10 kHz exclusion. A zero-power surface scores zero. The relative height makes the statistic invariant to overall gain. It asks whether the shape is peaked anywhere in the signed interval without requiring the peak location to match the receiver's CFO. The earlier formulation ranked signed CFO proposals. The old occupancy screen used broadband power flatness, peakiness and time-domain repetition with 20 ms stock labels. [Native cyclic comb](cyclic-carrier.md) · [Earlier occupancy screen](occupancy.md)

The minimum score on actual 12 ms positives in North visits 0–31 fixed the live threshold at **0.0426468909**. Ties pass. Visits 32–63 of the same resident public member were held. The dense comparison joins original cyclic scores and original 12 ms signed tuples from the first 24 visits by visit, radio, edge and I/Q digest. Sixteen of its 48 common lanes were scheduled full anchors and excluded. The independent physical DS26 weak comparison joins the same archived measurements on all 18 stereo clips and forces 12 ms on both radios. These clips intentionally sample weak challenges and supply only two empty outcomes. An empty lane here means the original short receiver issued no verified factor.

| Cohort | Actual short positives / empties | Calibrated missed positives | Calibrated skipped empties | Hindsight skipped empties at full recall |
|---|---:|---:|---:|---:|
| North calibration | 23 / 25 | 0 | 1 | 1 |
| North held | 35 / 29 | 0 | 0 | 2 |
| Physical dense DS30-0008 | 21 / 11 | 3 | 2 | 1 |
| Physical weak DS26 | 34 / 2 | 4 | 0 | 0 |
| Planted persistent / noise or silence | 4 / 8 | 0 | 4 | 8 |

All three dense misses were receiver 0 and negative CFO, from **−411 to −65 kHz**. Weak misses included one receiver 0 negative CFO near **−237 kHz** and three receiver 1 positive CFOs between **+406 and +465 kHz**. On the deterministic controls, both signed radios on both pilot edges retained their persistent carrier. The threshold skipped all four silent lanes and kept all four white-noise-only lanes. The full-recall dense and weak cutoff scores were 0.02153 and 0.01033, respectively. At the lower common cutoff neither held physical panel skipped any empty lane. The ROC is descriptive for these authenticated slices and this statistic. [Exact lane identities and thresholds](measurements/cyclic-presence.json.gz)

## Paid clocks and resource boundary

The North member matched every released scheduled factor byte on both radios, including the 16 full anchor calls. Four alternating-order resident passes measured the native baseline and both cyclic paths. Whole-stage screened clocks charge the measured screen on every short lane and the measured original call where routed. Both stages charge unchanged anchor work. These are detector-call reconstructions over identical measured inputs.

| Paid comparison | CPU / elapsed |
|---|---:|
| Held North original short mean per lane | 1,025.09 / 1,025.71 µs |
| Held North comb export plus original normalization | 69.18 / 69.25 µs |
| Held North comb with four-peak shape gate | 84.17 / 84.25 µs |
| Held North original 64-short-lane subtotal | 64.850 / 64.887 ms |
| Held North calibrated subtotal | 70.184 / 70.227 ms |
| Held North hindsight full-recall subtotal | 68.590 / 68.633 ms |
| Whole North member with original anchors, direct | 136.162 / 136.218 ms |
| Whole North member with original anchors, calibrated | 144.766 / 144.831 ms |

The archived four-peak callback averaged **78.88 µs CPU** on the dense join and **78.75 µs CPU** on weak. Prior measured weak 12 ms baseline totaled **43.867–47.056 CPU ms** over the 36 lanes. The exact weak acquisition mean-cost calculation needs **79.9%** of empties skipped for a free screen, **89.3%** at 66 µs and **91.9%** at the held North 84.17 µs. It charges every one of the 1,240 short opportunities and estimates savings from the previous mean per-call cost. It is a workload projection, separate from the observed slices. Even a cost-free score with the measured dense full-recall separation is far below that target. [Signed weak cost and exposure](quiet-cycle.md)

The dense origin stayed closed after passive admission found only 84 of 18,907 payload pages and zero of 43 index pages resident on its first member. The saved DS26 ZIP had 5,474 of 5,476 pages resident and also stayed closed. Both physical cohorts therefore use their original authenticated archive joins. The first attempt stopped at the weak residency check before any lane measurements. The completed run read only the existing North tmpfs member, generated its small synthetic controls and opened the two sealed receipt files. Intake charged 273.3 CPU / 274.3 elapsed ms and zero process storage input. No waveform collection, cold physical input or solver ran.

## Reproduce

Under the exclusive Gauss lock and environment in [the saved waveform study](tail-confirm.md), run `-m reports.ALGO08.v3.cyclic_presence NEW_TMPFS_DIRECTORY` from the research worktree. The runner builds the existing comb and performs a waveform pass only on admissible resident input. The dense and weak quality join remains available from the checked source receipts. Four focused tests passed. The uncompressed result SHA-256 is `5d0abdb95f9b1260fa4f4b0f33106a1837f2996b87fb6b187c23b1abf778e0b6`. [Runner](cyclic_presence.py)
