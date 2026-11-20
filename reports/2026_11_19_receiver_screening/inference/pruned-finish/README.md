# Pruned aligned v5 finish

The pruned finish reproduced both aligned-v5 coordinates and frequency objectives exactly on all six recordings. It also preserved the residual addition, reassociation, and associated observation counts. Conditional Doppler RMS matched exactly in both arms on the five recordings that publish it. The two fresh control pairs reproduced every eligible family score. [Sealed results](receipt.json) · [Position and frequency scores](scores.csv)

The residual addition screen now checks that every required held-time partition can exist and that the incumbent has room under the two-family cap before computing an orbital grid. The final reassociation rank computes leave-one-out RF influence only for families meeting the original support requirement of at least 30 points and two tracks. The retained candidates still face the original scoring, additions and reassociation rules. [Implementation](../../../../tools/pipeline_eval/variants/v5_pruned_finish.py) · [Protocol](PROTOCOL.md)

The four challenge recordings use authenticated archived aligned-finish predictions from the same scientific requests. The two ordinary recordings were chosen by a recording-ID hash without looking at positions or frequency fit, and each ran a fresh aligned control and a fresh pruned worker on the same logical CPU. Every replay starts from archived native factors and retains both calibration arms. [Archived aligned controls](../../armijo-finish/aligned/positions.jsonl.gz) · [Measurement harness](../../../../tools/pipeline_eval/qualification/pruned_finish_eval.py)

All six fixes fell within 2 km in both calibration arms. Median geographic error was 0.564 km at zero calibration and 0.547 km with fitted calibration. DS26-0287 supplies both frequency objectives and omits conditional RMS. The other five have both RMS values in the position outputs. [Geographic and frequency evidence](scores.csv) · [Control and candidate chart data](figures.json)

## Work and runtime

Across the six recordings the pruning rules reduced the residual targets that reached numerical screening from 18 to 15 and the per-arm omission builds from 250 to 164. All three skipped targets lacked a required held-time fold. The omission counts on both fresh controls independently match the original-work counts derived from the candidate's support ledger. The separate 135-recording archive audit measures structural eligibility across the original v5 outputs. [Work counts](timings.csv) · [Archive eligibility audit](audit/README.md)

| Recording | Residual targets, offered → evaluated | Eligible / observed influence families | Per-arm omission builds, original → pruned | Checked residual addition | Reassociation |
| --- | ---: | ---: | ---: | --- | --- |
| DS26-0066 | 3 → 3 | 16 / 20 | 40 → 32 | 67 added in each arm | 62025 → 68047 |
| DS26-0287 | 3 → 2 | 15 / 23 | 46 → 30 | 32 added in each arm | Incumbent retained |
| DS26-0002 | 3 → 2 | 16 / 27 | 54 → 32 | Rejected | Incumbent retained |
| DS29-0082 | 3 → 2 | 6 / 17 | 34 → 12 | No qualified new family | Incumbent retained |
| DS26-0175 | 3 → 3 | 14 / 16 | 32 → 28 | No qualified new family | Incumbent retained |
| DS29-0357 | 3 → 3 | 15 / 22 | 44 → 30 | No qualified new family | Incumbent retained |

| Fresh pair | Logical CPU | Ranking CPU s, aligned → pruned | Whole CPU s, aligned → pruned | Whole wall s, aligned → pruned | Numerical process peak RSS KiB, aligned → pruned |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0175 | 20 | 5.45 → 4.67 | 202.85 → 195.72 | 208.67 → 198.38 | 1,572,176 → 1,582,380 |
| DS29-0357 | 22 | 11.43 → 11.02 | 215.06 → 229.49 | 219.86 → 231.91 | 1,576,736 → 1,525,812 |

Ranking CPU fell in both fresh pairs. Whole-worker CPU and peak memory moved in opposite directions across the two recordings. Both methods computed the same 99 residual nomination grids and one catalogue propagation per fresh recording. The three recordings with residual work removed use historical controls, so the residual work counts give the comparison for that stage. Stage measurements include the process RSS high-water mark at the end of that operation. The complete schedule returned its last worker receipt 1,087 seconds after locking. [Detailed stage measurements](timings.csv) · [Source and input lock](source-lock.json)
