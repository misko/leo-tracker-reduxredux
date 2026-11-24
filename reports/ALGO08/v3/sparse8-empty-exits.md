# How early must an empty 8 ms lane be recognized?

The first 30 paired recordings are the development group. Giving a perfect empty-lane classifier the results of the lag search before it decides saves 95–100 s across those recordings, depending on which measured receiver prefix supplies the relative stage costs. Even with a 1.4× faster complete solver, that projects to less than 1.92× summed speed. This gives an upper bound within the timing model. A real classifier pays for its decision and can lose detections.

Apply the same two donor profiles, the same 1.4× whole-solver assumption and the same post-lag decision point to frozen positions 31–46. Keep every positive short call, every full anchor, all failed and withheld costs, and the original candidate's positions. For comparison, price perfect knowledge before the callback, before lag processing, before refinement and before verification. The previously reported end-to-end clocks and detection totals are available. The held recording-level empty fractions and their stage-weighted transfer have not selected these decision points. [Measured stage profile](sparse8-native-profile.md) · [Signed first-30 lane census](first30-empty-call-roof.md)

## Result on the next 16 and all 46

| Last measurement available before deciding | First 30 summed speedup | Next 16 summed speedup | All 46 summed speedup |
|---|---:|---:|---:|
| None, before even loading the lane | 1.999–2.003× | 2.088–2.092× | 2.031–2.035× |
| Input filtering and frame modes | 1.960–1.966× | 2.045–2.052× | 1.991–1.997× |
| Lag timing | 1.914–1.920× | 1.994–2.001× | 1.943–1.949× |
| Carrier search and seed setup | 1.880–1.887× | 1.957–1.965× | 1.908–1.915× |
| Pilot confirmation | 1.823–1.835× | 1.895–1.908× | 1.850–1.862× |

On the next 16, the post-lag exit narrowly passes both timing gates with one donor and misses both with the other. Across all 46 it still needs **58–65 s** for the summed gate, even with perfect decisions, a free gate and the assumed solver improvement. The corresponding paired median speedups are 1.997× and 2.005×. An early rejection driven only by a lag score cannot supply the missing combined savings under these assumptions. A genuine method that accelerates positive calls, full anchors or input handling could change that conclusion.

The endpoints of each range come from applying the 0163 and 0419 timing profiles separately. For each recording, the calculation weights positive and empty stage CPU by their actual counts, then applies the avoidable empty-stage fraction to measured short-callback wall time. A post-entry decision retains all unassigned bookkeeping. Every returned position remains exactly the candidate's by assumption. The first 30 had **16,826** short lanes where the candidate returned empty and the installed receiver found a factor. Preserving the candidate's empty decisions leaves that source of disagreement in place. [Field agreement](first30-empty-call-roof.md) · [All timing gates and case groups](measurements/sparse8-empty-exits.json)

Run `python -B -m reports.ALGO08.v3.sparse8_empty_exits CAMPAIGN` using the original DS30 receipt directory. This reads measured metadata. It requires no waveform, ephemeris, or timing lease. [Calculator](sparse8_empty_exits.py)
