# Would the first satellite assignment preserve the named DS30 fixes?

Always taking the first proposed assignment agrees with ALGO08v3 on **all four** of the initial DS30 recordings. Across the signed 100-recording panel, **19 of 92 completed fixes** chose another assignment. Twelve chose the second and seven the third. A rule that skipped the other assignments on the strength of the first four examples would change the selected branch on 20.7% of completed fixes. The saved score records establish branch changes. They contain no position counterfactual for the discarded rank-zero branch. [Reproducible census](named_rank_census.py) · [Signed-source pins and per-recording outcomes](measurements/named-rank-census.json.gz)

| Frozen assignments | Completed fixes | First / second / third chosen on completed fixes | Median timed nomination CPU | Sum of measured nomination / corresponding process CPU |
|---:|---:|---:|---:|---:|
| First 4 | 4 | 4 / 0 / 0 | 1.515 s | 12.744 / 334.883 s (3.81%) |
| First 16 | 15 | 13 / 2 / 0 | 1.695 s | 31.823 / 1,248.253 s (2.55%) |
| All 100 | 92 | 73 / 12 / 7 | 1.224 s | 152.305 / 7,338.544 s (2.08%) |

The named screen’s CPU clock covers its early fits, the winner’s subsequent phase refreshes and final metrics. A winner-only shortcut still has to fit the chosen hypothesis. DS30-0008 spent 8.963 CPU seconds here, the largest recorded value; the other three initial recordings spent 1.695, 0.752 and 1.334 s. For all 100 assignments, 93 supplied a timer, including one eventual withholding. Two other withheld recordings and five solver failures supplied no timer. These are named v3 clocks. The current short receiver and its solver have their own stage timings, and the 2× goal uses whole-process elapsed. [Named implementation and clock boundary](../../../tools/pipeline_eval/variants/v5_screen_winner.py)

The first two nonzero winners were DS30-0402 and DS30-0245. Their second assignments beat the first by **47.78** and **189.78** objective units at screening. Across all 19 changes the winning margin ranged from **7.63 to 1,729.18**, with median **75.53**. The largest advantage was 6.64% of the first candidate’s score. These margins are available after fitting the competing assignments. They cannot be used to decide for free, before the fit, which ones to run. The dense recent-positive experiment also showed that a branch can overtake the early leader after further optimization. A useful speed comparison should include a nonzero-winner control in addition to the dense slow case. [Dense counterexample](causal-mask-dense.md)

The census verified the enrollment manifest, final comparison digest and all 100 pair digests. It read measurement metadata only. It did not read waveform data or run any localization solves.
