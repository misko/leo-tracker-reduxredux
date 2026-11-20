# Initial-support majority in the 78-source standalone receiver

The cloned standalone kept both containing fixes exactly and stopped both previously observed far wrong-tile publications before conservative recovery. The separate archived near omission still published a false fix in both arms. It had 83.9% compatible initial support and exactly reproduced the ungated position and frequency endpoints in a same-core live pair. This is a diagnosed replay of previously examined inputs. [Protocol](PROTOCOL.md) · [Prediction seal](prediction-lock.json) · [Scores and paired timing](scores.json)

## Input and implementation boundaries

The qualification copied the sealed 78-source package to its own bulk workspace and changed one source leaf, `v5_direct_cavity.py`. The existing predicate is embedded verbatim and runs after the original initial winner is selected. It reads that winner's `c = 0` compatibility receipts and accepts when `2 * accepted_points > tracked_points > 0`. The standalone then enters its original paired conservative and cavity path. A rejected request emits an explicit paired withholding. Its only fitted state is the initial incumbent, and the receiver exposes no coordinate for it. The copied native manifest was rebound to the copied build; the native bound and projector binaries retained their hashes. The published package and previously scored artifacts were unchanged. [Executed leaf](as-executed-v5-direct-cavity.py.txt) · [Source and binary lock](source-lock.json)

The four primary requests use the exact original native files, session, clock, track configuration, skyline screen, causal orbit collections and offered tiles. The fifth offer reuses the previously reviewed southern near-omission capture with its earlier causal history and screen at the offered center. Its ungated control was freshly run on the same core and the same prepared native input. The pre-run lock independently binds the physical scoring references in geodetic coordinates and ECEF. Only the explicit receiver inputs enter the numerical request. All trials start at complete stored native GLRT and reconstruct their own tracks and associations. [Frozen requests](requests.json) · [Scoring targets](scoring-targets.json) · [Earlier standalone transfer](../cavity-payload-transfer/README.md) · [Earlier near-omission evidence](../edge-interval/README.md)

## Coverage, position and RF

The two calibration values in each cell follow zero/fitted `c`. Candidate and stock endpoints are exactly equal on every offer that passes the gate. Conditional RF RMS is recorded separately from the measured geographic errors. The admitted near omission illustrates that good original support and low conditional RF can accompany an incorrect tile.

| Previously examined offer | True signed margin, km | Compatible initial points | Gated disposition and position error, km | Ungated position error, km | Conditional RF on the admitted outputs, Hz |
|---|---:|---:|---|---:|---:|
| 36.79°N, containing | +3.643 | 1,092 / 1,092 | Published 2.121 / 2.103 | 2.121 / 2.103 | 86.023 / 85.998 |
| 36.79°N, far omitted | −54.004 | 337 / 1,092 | Early withheld | 65.890 / 65.890 | — |
| 13.79°S, containing | +4.132 | 625 / 1,067 | Published 1.614 / 1.491 | 1.614 / 1.491 | 63.250 / 63.204 |
| 13.79°S, far omitted | −40.922 | 383 / 1,067 | Early withheld | 53.911 / 53.605 | — |
| 43.42°S, archived near omission | −1.513 | 899 / 1,072 | False fix 5.558 / 5.600 | 5.558 / 5.600 | 63.476 / 63.488 |

For each arm the primary containing coverage was 2/2 for both versions. The previously observed primary far false fixes went from 2/2 to 0/2. The archived near false fix remained 1/1 under both versions. Original stock far RF RMS was 87.316/87.207 Hz and 65.693/65.932 Hz. Both gated far cases issued a clean abstention with no coordinates or later-stage RF scores. [Zero-calibration figures](figures/c0/transfer.pdf) · [Fitted-calibration figures](figures/fitted_c/transfer.pdf)

## Bounded stage witnesses and elapsed cost

All six live workers completed in 96.12 s with 512 MiB cgroups, zero swap, nice 10 and one numerical thread apiece. Each gate had an observed duration of 0.33–0.52 ms, including measurement overhead. Stage traces witnessed entry to `initial_support` on all gated requests and no entry to conservative recovery on either rejected far request. The omitted candidates took 25.82 and 24.12 s wall versus 40.13 and 35.70 s for the prior exact-input control. The original stages after initial selection accounted for 14.26 and 13.31 s, respectively. The corresponding whole-worker CPU values were 25.09 versus 38.58 s and 23.48 versus 35.17 s. These comparisons use archived timings on the same input and core. [Raw stage and cgroup witnesses](predictions.json)

The containing gated workers took 31.09 and 31.93 s versus archival 28.99 and 30.15 s, so their host timing difference exceeds the observed predicate cost. The same-core archived near pair took 35.15 s gated and 36.85 s ungated. Both ran all original fit stages. No timing reduction is required for an admitted request. [Per-stage and resource differences](scores.json)
