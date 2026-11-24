# DS30-0016 first-member shorter-scout impact

The 12 measured shorter-scout omissions from the first physical member
changed neither calibration arm's position, terminal RF residual nor owner
roster on the complete saved 808-visit DS30-0016 recording. All 116 ordered
observation, family and role entries were identical in each arm. The
ordinary saved control also reproduced the original full unrefined
publication's terminal digest.

| Full saved input | Factors | Held gain, radios 0/1 (nats) | Fixed-`c` error (m) | Fitted-`c` error (m) | Fixed/fitted RF RMS (Hz) |
|---|---:|---:|---:|---:|---:|
| Original unrefined 20/12 ms | 475 | −15.273 / −8.948 | 1,311.046 | 1,694.025 | 121.526 / 120.291 |
| First member with measured shorter-scout omissions | 463 | −14.148 / −9.258 | 1,311.046 | 1,694.025 | 121.526 / 120.291 |

The first member contains 64 issued visits, 58 admitted stereo visits and
116 native lane rows, with 45 gated factors ordinarily and 33 under the
shorter scout. Radio 0 lost 9 of its 20 short factors, and radio 1 lost 3
of 14. No full-anchor factor changed. None of those 12 signed lane IDs
intersected either full unrefined baseline owner roster. The held-anchor
selector stayed on the unfiltered route for both inputs. The experiment
used saved pre-tail evidence and made zero waveform or CFO refinement calls.

## Authenticity and publication

The archived scout result, both reversed pairs, signed first-member source
manifest, compressed/index identities and ordered decoded window digests
are bound in the receipt. Both prefix packets matched the full recording's
original epoch and first 64 delivery clocks. All chronological slot metadata,
factor eligibility, rank, signed CFO, integer and fractional epochs matched
between the full and guarded ordinary prefix. Only the three score fields
differed, at maxima 1.265e−13 exact, 6.272e−14 control and 1.893e−13 margin
against the earlier 1e−10 score certificate. For every lane where the two
guarded scout arms agreed, the splice kept the original full-recording row
byte for byte. The 12 empty lists came directly from the independently
measured shortened replay, unchanged in both orders. All later rows were
left intact and the new signed research recipe binds both parents. The two
packets and choices were sealed before either solver ran.

Both saves used the original containing offer, raw authority, inventory and
causal archive. Both used the corrected portable orbit index (19 sidecar
hits), grouped exact catalogue rank (48 compact profiles, no rank fallback),
and accepted original survivor fit. The signed path and complete 179-point
grid matched scientifically in both calibrations, with each sidecar bound
to its own terminal and position PNG. All eight PNGs per publication were
verified. The position and track-RMS PNGs were identical in encoded and
decoded content. The six receiver figures changed.

| Measured saved scope | Ordinary | First-member shorter |
|---|---:|---:|
| Fresh worker launch through exit (wall s) | 4.250 | 4.376 |
| Worker CPU (s) | 4.221 | 4.373 |
| Numerical solve CPU (s) | 2.138 | 2.189 |
| Filesystem input blocks | 4,760 | 184 |
| Held selector CPU (s, paid in preparation) | 0.015 | 0.028 |

One joint preparation process cost 0.288 s wall. Its input verification and
splice cost 0.022 s CPU, inside 0.076 s for preparation, both selectors and
both packet seals. Separate font setup cost 0.170 s wall. The saved clocks
have unequal process page-in and contain no detector workload. This one
prefix intervention leaves the failed original physical scout gate in force.
The reported 27.6% first-member native short-phase CPU reduction and these
saved endpoints do not establish whole-recording savings or accuracy for a
receiver using the shorter scout on every member or paying fixed-epoch
refinement.

## Reproduction

The [frozen protocol](first-member-scout-protocol.md) was committed at
`a02777ff5`, clarified before solving in `161cb9861`. The
[trial](first_member_scout.py) ran at `80aea0712` with one fresh tmpfs
destination on Gauss under the existing lock, CPU2, nice 15, I/O priority 7
and one numerical thread. Subcommands are `launch`, `seal` and `score`,
using the released Python and the original installed/local source paths.
The [receipt](measurements/first-member-scout.json.gz) preserves the exact
inputs, both exit clocks, both scientific and media bindings, and the
post-exit score. Three focused `test_first_member_scout.py` tests cover
exact projection, signed roundoff rejection and anchor protection.
