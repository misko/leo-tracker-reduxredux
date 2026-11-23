# North held-anchor original-input replay

The cumulative held-anchor CLI finished in **12.023 s elapsed and 12.018 s CPU** on the previously scored public North signed simulation. The named ALGO08v3 comparator finished in **16.761 s elapsed and 16.757 s CPU**. This matched pair used the original containing offer and a warm single-core slot. The cumulative arm used 28.3% less CPU and had a 1.39× elapsed speedup. The timing covers the entire cumulative receiver and solver path, including publication and exit.

| Process measurement | Named v3 | Held-anchor cumulative |
|---|---:|---:|
| Launch to verified detector file, s | 8.1545 | 6.2451 |
| Effective acquisition, compressed MB/s | 193.69 | 252.91 |
| Launch to terminal, s | 14.8844 | 10.0447 |
| Launch to standard report, s | 16.5685 | 11.5104 |
| Process exit elapsed, s | 16.7607 | 12.0232 |
| Whole process CPU, s | 16.7566 | 12.0180 |

Effective acquisition divides 1,579,423,424 original compressed bytes by launch-to-detector time. The boundary includes setup, receiver authentication and the handoff file in both processes, plus selector and history replay in the candidate. The cumulative arm measured 5.2300 CPU s and 5.2312 elapsed s for authenticated acquisition before selection. The held route cost 0.0441 s elapsed including the selected chronological replay and sidecar. Both launches had 19 of 19 verified compressed members and 385,609 of 385,609 resident pages, with zero input blocks and zero major page faults observed.

| Estimate | Named v3 position error, km | Held-anchor position error, km | Named v3 RF RMS, Hz | Held-anchor RF RMS, Hz |
|---|---:|---:|---:|---:|
| Fixed `c = 0` | 0.105690 | 0.127778 | 5.406434 | 6.880727 |
| Fitted `c` | 0.140779 | 0.113418 | 5.166631 | 6.763598 |

Against named v3, the candidate gained 27.4 m in fitted-`c` position error and lost 22.1 m in fixed-zero position error. RF RMS increased in both corresponding comparisons. Within the held-route packet, fitting `c` reduced error by 14.4 m and RMS by 0.1171 Hz. Within named v3, fitting it increased error by 35.1 m and reduced RMS by 0.2398 Hz. These observations are retrospective and apply to this one simulation and containing offer. The raw pair measures the cumulative CLI as a whole, so timing and localization comparisons do not isolate the selector’s treatment effect.

## Execution and verification

The frozen cumulative entry was `0d0b2ad9f5f44aaf56c04d77bb2ab226d03b912e`, SHA-256 `025b727d423c0b7b33f5d7036dc0e9bc97ba30fcc07d454599679958e140adca`. It enabled the existing `--prove-empty-graph --one-pass-web-png --exact-graph-reuse` path and the new `--held-anchor-route` option. The named launcher and candidate ran once each under the shared Gauss lock on CPU 2 at nice 15 and best-effort I/O priority 7, with one numerical thread, common font cache and fresh tmpfs output roots. Named v3 ran first, reversing the earlier North raw pair. The two commands were run under the public recording owner so that Linux could authenticate the read-only pre-launch page census. No physical waveforms were opened.

Both launches bound the original authority, 1,200 issued and processed stereo visits, the same 2,400 probe opportunities and the same causal cutoff. The original mixed 20/12 ms packet matched archived `2b4e1282…`. Positive held log-score gains on radio 0 and radio 1 were 28.3664 and 26.3449. The candidate selected the original chronological history packet `a03fefaf8…` with 456 populated probe rows. The sidecar’s source, recipe, route and packet digests matched the archived North control and were sealed before the selected packet reached publication. The archived weak control independently retained `c09de017…` with 475 factors.

The live candidate recorded one authenticated traversal, one verified handoff and one ordinary graph solve. Each launch produced both finite calibration arms, a complete 137-point grid, its own position path and grid digest bound to its own position PNG, and eight dimension-matched PNGs verified through full RGBA decode. Named v3 matched its archived terminal, detector packet, owner digests, scientific sidecars and eight encoded figures. The sealed publication data precede the public simulation score. This pair does not promote a release.

Frozen records are archived with the report. File SHA-256 values before lossless compression are `7a077f22f27d506c8c3ae9156467d6dfa675cf79ac4d504e88742add0519d4f5` for the launch binding, `87c644ca50ee678f0a4eeb097ff4195cd1fc4157806d92ff3a405d45c98f08f2` for the sealed verification and `60e1bfa8e85fce58b6169e33a44d66e80f58abfdac37092d1065b0e527d91de2` for scoring. [Protocol](north-held-anchor-pair-protocol.md) · [Launch binding](measurements/north-held-anchor-binding.json.gz) · [Sealed receipt](measurements/north-held-anchor-sealed.json.gz) · [Score](measurements/north-held-anchor-score.json)
