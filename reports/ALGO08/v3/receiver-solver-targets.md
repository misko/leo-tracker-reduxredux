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
