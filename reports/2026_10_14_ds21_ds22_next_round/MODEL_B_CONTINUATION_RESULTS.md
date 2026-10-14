# Likelihood-width continuation: improved objective, unresolved positions

The fixed broad-to-original continuation completed all 24 planned calls, all
stationary, across the two original worst cases. Every final was evaluated under
the exact original likelihood and priors. The broader intermediate likelihood
finds lower-objective final solutions in all six views, but full-band position
changes are small and mixed. This is not a localization fix to promote.

|Case|View|Matched control km|Broad-to-original km|
|---|---|---:|---:|
|039|CH1–8|8.599847|8.448440|
|039|CH1–4|2.917469|3.773634|
|039|CH5–8|20.117621|13.000754|
|023|CH1–8|5.599817|5.799471|
|023|CH1–4|29.635673|25.729405|
|023|CH5–8|10.458750|9.006544|

On 039, CH1–8 remains much worse than CH1–4. On 023, CH1–8 remains better than
both halves but is far above 0.5 km. Full-band original-objective reductions are
115.708579 and 20.585789; NLL reductions are 105.161424 and 19.685851. Their RMS
residuals worsen from 98.244767→100.532061 Hz and 94.674183→94.879206 Hz.
Lower training objective does not establish lower position error or residual
RMS. The outcome supports a local optimization limitation but does not make it
the main explanation for multi-kilometre errors.

Both conditions have two calls from identical original per-view stationary
winners, in matching new 25 km disks, each capped at 20 seconds/600 iterations.
Control uses observation-sigma factors 1→1 and alternative 2→1. All other
parameters, priors, bank and observations remain unchanged; fitted c is retained.
These half views inherit shared all-channel discovery. This is a warm-path
experiment, not a full independent-half or six-start algorithm benchmark.

Whole-case runtimes were 33.963625 s (039) and 19.233480 s (023), including
preparation. All launch/result/termination receipts are retained. There were no
retries, failed calls or nonstationary final estimates. The original control
positions reproduce the original selected states to numerical precision.
Both cases sealed before the reference join, with no held data used. Results
measure distance to the configured reference, not an independently surveyed site.

Receipts: local/model-b-width-continuation-039-v1 and
local/model-b-width-continuation-023-v1. Terminal hashes are
3dc315ec16c1b9d21d4bd2d04a46c90a850d2a8f2991fd2f6af1e415567f1358 and
f5f94871a9c690ee73e9e39cccc12e1594a174c0fe94ca850714dfd4c2dab17f.
Source implementation eb4af3159; authority/evaluation tests 03ac02f9d.
Four component tests and Ruff passed. No original scientific source changed.
