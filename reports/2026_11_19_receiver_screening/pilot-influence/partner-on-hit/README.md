# Separating partner observations on primary hits and misses

The eight hard-pilots recordings compare four antenna conditions on the same waveforms and RF schedule. The alternating primary starts on physical lane zero at each RF and keeps its full fixed-four candidate list. The partner can be omitted, retained only after a primary hit, retained only after a primary miss, or retained every visit. A hit uses the existing strict fractional gate. Hardware-invalid visits retain their exclusion and leave the RF alternation unchanged. The partner-on-hit condition preserves both full lists after a hit and keeps an empty physical partner slot after a miss. [Frozen protocol](PROTOCOL.md)

The observed support has three parts. Every cell retains primary gates. Partner-on-hit adds gated observations from visits where both physical lanes detected a candidate. Partner-on-miss adds gated observations from visits with a negative primary and a positive partner. The both-lane cell contains all three. The inputs of the two earlier projections reproduced byte for byte before the study launched. Their terminal positions and the authentic both-lane controls bind the same recording, fixed-four detector parent, causal request and tile. [Frozen input and call ledger](packet-audit.json)

The eight newly constructed cells ran in the same installed compact phase-release receiver, one numerical thread on CPUs 6–11, 512 MiB, no swap, and a 210 s cap. Each fit returned or withheld both calibration arms through the ordinary position entry. The logical call counts follow the frozen schedule. The new measured timings cover stored native factors through position, with no detector execution in this replay. [Resource receipts](resources.csv)

The paired error and conditional RF effects report adding each partner observation class while holding the other class present or absent. The interaction subtracts the effect of adding partner-on-hit under primary-only support from its effect when partner-on-miss is already present. A more negative error change means a closer geographic estimate. The per-recording tables preserve all eight cases, both calibration arms and all four original v5 reference roles. [Position and RF scores](scores.csv) · [Per-recording effects](effects.csv) · [Original v5 roles](capture-era-v5.csv) · [Position chart](charts/README.md)

## Results

All eight new fits returned positions in both arms. The 52,126 valid stereo visits included 17,736 primary hits, 12,355 additional partner hits on those same visits, and 5,355 partner-only hits. Another 2,052 hardware-invalid visits stayed excluded. The counts below are for the eight recordings combined. [Per-recording support](support.csv)

| Condition | Logical detector calls | Retained observations | Median error, km `c = 0` / fitted | Median conditional RF RMS, Hz `c = 0` / fitted |
| --- | ---: | ---: | ---: | ---: |
| Alternating primary only | 52,126 | 17,736 | 0.871 / 0.890 | 90.890 / 90.845 |
| Partner on hit | 69,862 | 30,091 | 0.691 / 0.758 | 83.834 / 83.844 |
| Partner on miss | 86,516 | 23,091 | 0.908 / 1.141 | 88.059 / 88.051 |
| Both stock lanes | 104,252 | 35,446 | 0.737 / 0.814 | 83.979 / 83.917 |

Adding co-observed partner hits to primary-only support improved seven of eight recordings in both arms, with median paired gains of 220 m at `c = 0` and 246 m with fitted `c`. Adding those co-observed hits when partner-only misses were already retained improved all eight, with median gains of 276 m and 402 m. Adding partner-only observations to primary-only support improved five of eight at `c = 0` and three of eight with fitted `c`. Adding them after co-observed hits worsened each of the six challenge recordings in both arms. Across all eight, the latter contrast increased median error by 56 m and 91 m, and improved one recording in each arm. The median interaction was +62 m and +76 m. [Paired effects summary](effects-summary.csv)

DS29-0082 was the exception when adding hits to primary-only support. Its fitted error was 0.728 km with primary alone, 1.971 km with partner on hit, 2.802 km with partner on miss and 2.346 km with both lanes. The six challenges had one fitted partner-on-hit result within 10% of the original no-repair baseline error. The other three antenna cells had zero. The eight-recording result is evidence for these recordings under this solver and dispatch schedule. [All scientific scores](scores.csv)

Adding co-observed hits to primary-only support lowered median paired conditional RF RMS by 7.65 Hz and 7.58 Hz in the two arms. Adding partner-only observations on top of hits changed median RF RMS by +0.12 Hz and +0.15 Hz. The new numerical services ran for 34.5–92.2 s, with median wall and CPU times of 60.4 and 57.9 s. Peak cgroup memory reached 436.9 MiB, with zero swap. [Measured post-detector resources](resources.csv)

## Reproduction

Run `python -m tools.pipeline_eval.qualification.partner_on_hit_trial /path/to/new/local/work` with the authenticated source archives and no existing plan. After the prediction lock is created, run `python -m tools.pipeline_eval.qualification.partner_on_hit_results /path/to/work --plot /path/to/plots`. [Prediction lock](prediction-lock.json) · [Figure lock](figure-lock.json)
