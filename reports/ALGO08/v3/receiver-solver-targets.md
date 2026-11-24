# How much faster must the receiver and solver become together?

On the first 30 DS30 pairs, a **1.5× faster native receiver callback and a 1.4× faster complete solver** would just meet both end-to-end wall-time targets if every other interval and scientific outcome stayed fixed. The observed candidate spent 477.043 s in native callbacks and 504.638 s in the solver, with 302.627 s to save to halve the 2,788.109 s ALGO08v3 total. The solver interval covers preparation, proposals, evidence and any fallback. The callback interval excludes reading, decoding and authentication. [Measured stage boundaries](first30-after-intake.md)

| Assumed speedup of both native callback modes | Required whole-solver speedup | Required speedup when changing only accepted and rejected proposals | Required speedup when changing only accepted proposals |
|---:|---:|---:|---:|
| 1.00× | 3.007× | Unreachable | Unreachable |
| 1.25× | 1.697× | 14.439× | Unreachable |
| 1.50× | 1.398× | 2.817× | 3.726× |
| 2.00× | 1.146× | 1.404× | 1.485× |

The figures are rounded to three decimals. Each column is an alternative change to the original measured candidate. For each recording the calculator scales the measured callback wall time and the specified solver scope independently. It finds the minimum solver reduction satisfying both the summed and median paired time ratios, with ties at half time accepted. The calculation retains failures, withholds, independent verification and capture order. It assigns no accuracy benefit to speed and assumes the saved wall time translates one for one to the complete process. [Calculator](receiver_solver_targets.py) · [Signed input](measurements/first30-after-intake.json.gz)

The next check applies the **fixed 1.5× callback and 1.4× whole-solver design point** to positions 31–46 of the original benchmark schedule. The total measured speed and accuracy of that group were already available. Its stage-by-stage result was not used to pick these two rates. This check tests whether the same engineering budget transfers to a different workload. Delivering those stage speeds and preserving actual positions requires a new paired implementation.

## Check on the next 16 recordings

| Frozen schedule positions | Observed summed / paired median speedup | Native callback / complete solver wall seconds | Projected summed / paired median speedup at the fixed design point | Projected seconds below half the ALGO08v3 total |
|---|---:|---:|---:|---:|
| First 30 | 1.643× / 1.718× | 477.043 / 504.638 | 2.001× / 2.051× | 0.570 |
| Next 16 | 1.739× / 1.714× | 283.852 / 227.004 | 2.085× / 2.086× | 34.188 |
| All 46 | 1.678× / 1.714× | 760.895 / 731.642 | 2.032× / 2.075× | 34.757 |

The next 16 gave the joint design more headroom. At the same assumed callback speed, they required a 16.17% cut in whole-solver wall time for both gates, versus 28.45% on the first 30. The first group had just 0.57 s to spare under this design, so small uncounted costs could erase its summed margin. The two groups are separate recordings from the same receiver site. No implementation achieved the projected speeds in this experiment. The existing accuracy deficit would still need a separate repair. [Frozen design](https://github.com/misko/leo-tracker-reduxredux/blob/a88bd3228/reports/ALGO08/v3/receiver-solver-targets.md) · [16 per-recording measurements and source digests](measurements/receiver-solver-targets-next16.json)

Run `python -m reports.ALGO08.v3.receiver_solver_targets` to reproduce the development table. With authorized access to the campaign's timing metadata, add `--check-next-16 /srv/postgres-nvme/leo-ds30-evaluation-20261124` to reproduce the second group. The calculation reads saved receipts and requires no waveform or orbit replay.
