# Near-edge tile challenge on real roof recordings

On ten complete roof recordings, the original publication gates falsely published **3/20** omitted offers for the native smooth oscillator and **5/20** for the native fixed-training update. Each method published on two offers whose true site was 6 km outside the square. A nominal uncertainty-radius gate tested on six different recordings suppressed **zero** false fixes and cost each method one valid near-edge fix. Both calibration arms made the same publication decisions. [Frozen protocol](PROTOCOL.md) · [Primary summary](primary/summary.json) · [Reserve summary](reserve/summary.json)

## Primary challenge

The five DS26 and five DS29 recordings were selected by hashed ID, preferring recordings outside the earlier small development cohorts. Each recording was replayed with its original 25 km square and three newly generated squares. An independent hash chose one compass face and an along-face position for each recording. The site was 1.041–1.948 km inside or outside that face on the close offers and exactly 6 km outside on the third new offer. All recordings are from the same receiver site. The 20 omitted offers per method came in pairs on ten recordings. [Sealed evaluator labels](primary/evaluator.json) · [Inputs presented to the supervisor](primary/requests.json)

| Method | Original correct tile | True site 1–2 km inside | True site 1–2 km outside | True site 6 km outside | Recordings with an omitted publication |
|---|---:|---:|---:|---:|---:|
| Native smooth oscillator | 9/10 | 5/10 | 1/10 | 2/10 | 3/10 |
| Native fixed-training update | 10/10 | 6/10 | 3/10 | 2/10 | 4/10 |

The table below gives published median / P95 / maximum geodesic errors in kilometers. All fits, including withheld diagnostic positions and the counts within 1, 2, 5 and 10 km per scheduled cohort, are in the score summary. Fixed training published both omitted offers for DS29-0316. Each of the smooth receiver's three false publications came from a different recording. [Both calibration arms, by recording](primary/scores.csv)

| Method | Offer | `c = 0` error triplet | Fitted `c` error triplet |
|---|---|---:|---:|
| Smooth oscillator | Original | 1.453 / 2.651 / 2.822 | 1.226 / 2.385 / 2.541 |
| Smooth oscillator | 1–2 km inside | 1.350 / 3.932 / 4.554 | 0.848 / 3.971 / 4.628 |
| Smooth oscillator | 1–2 km outside | 4.548 / 4.548 / 4.548 | 4.678 / 4.678 / 4.678 |
| Smooth oscillator | 6 km outside | 12.111 / 12.933 / 13.025 | 11.997 / 12.728 / 12.809 |
| Fixed-training update | Original | 1.845 / 3.104 / 3.499 | 1.600 / 3.178 / 3.495 |
| Fixed-training update | 1–2 km inside | 2.959 / 11.176 / 13.041 | 2.509 / 10.992 / 12.988 |
| Fixed-training update | 1–2 km outside | 5.620 / 12.733 / 13.524 | 5.042 / 12.651 / 13.497 |
| Fixed-training update | 6 km outside | 12.703 / 12.968 / 12.997 | 12.616 / 12.909 / 12.941 |

Fitted `c` lowered the median conditional RMS on each offer class for both methods. On the smooth receiver's 6 km omissions, the median conditional RMS fell from 178.10 to 151.95 Hz while the same two positions were falsely published. All smooth false publications in the primary were at least 2.56 km inward from the offered boundary. Two smooth 6 km false fixes had zero-calibration held scores of 0.612 and 0.742. The existing boundary and held-track gates accepted these interior fits. [Primary position, frequency and gate distributions](primary/summary.json) · [Primary figure specification](primary/figures.json)

## Disjoint containment test

Fixed training reached the predeclared trigger of five false publications. The six reserve recordings were selected and their offers generated before any primary inference. The extra gate preserves the original publication decisions only when the supplied square also contains the full circle defined by the nominal covariance radius in both calibration arms. The table gives fixes before → after that extra gate, with the same counts in `c = 0` and fitted `c`. [Reserve evaluator labels](reserve/evaluator.json) · [Reserve figures](reserve/figures.json)

| Method | Original correct tile | True site 1–2 km inside | True site 1–2 km outside | True site 6 km outside |
|---|---:|---:|---:|---:|
| Native smooth oscillator | 5/6 → 5/6 | 4/6 → 3/6 | 1/6 → 1/6 | 1/6 → 1/6 |
| Native fixed-training update | 6/6 → 6/6 | 4/6 → 3/6 | 0/6 → 0/6 | 0/6 → 0/6 |

The two smooth false fixes were on the same recording, DS26-0070. The near omission produced a position error of 14.55 km with `c = 0` and 14.96 km with fitted `c`. The fitted centers were 9.58 and 9.30 km inside the offered square with radii of 2.83 and 2.84 km. The 6 km omission produced errors of 10.89 and 11.10 km with inward margins of 4.52 and 4.75 km and radii of 2.61 and 2.62 km. The local radius contained those erroneous solutions inside the tile. Both receivers lost the valid near-inside fix on DS29-0247. The reserve consists of different captures at the same site, with six east/west face challenges. [Reserve original-gate scores](reserve/scores.csv) · [Reserve containment scores](reserve/containment-scores.csv)

## Replay boundary and evidence

Every job scanned the complete archived native GLRT document, rebuilt the anonymous Graph and ran one of the two frozen receivers against one supplied square and causal TLE. The truth, condition and offsets were confined to the offer-maker and scorer and were never mounted in the isolated worker. For each capture the rebuilt Graph hash was identical across both methods and all four offers. The 32 fresh original-offer legs reproduced the archived physical arm outputs and decisions exactly. Opaque tile IDs were used throughout. [Primary prediction seal](primary/prediction-lock.json) · [Reserve prediction seal](reserve/prediction-lock.json)

The four single-threaded workers on CPUs 8, 9, 16 and 18 completed all 80 primary jobs in 98.12 s and all 48 reserve jobs in 75.43 s. The largest worker wall time was 7.41 s. Peak RSS was 154,368 KiB and peak virtual address space was 394,676 KiB. All completed under the 512 MiB address-space limit, with a 60 s per-job timeout and zero failed or timed-out jobs. The primary had a 720 s outer cap and the triggered reserve had a 590 s outer cap after the 98 s primary. The measured boundary starts at stored GLRT factors. The randomized tile shifts are new and the underlying RF is archived. [Primary roster and sources](primary/roster.json) · [Reserve roster and sources](reserve/roster.json)
