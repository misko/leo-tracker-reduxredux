# DS30-0280 held moment-preserving correction

On the preregistered rank-68 recording, the moment-preserving CFO correction reduced error by **22.96 m at fixed `c=0` and 26.20 m with fitted `c`** relative to the ordinary successor. Both saved cells published fixes. The ordinary replay matched the official raw successor terminal, ordered owners, Graph summary, signed grid, position path and all eight PNGs exactly. Both saved cells and their scientific verification sealed before the survey join. [Extended protocol](ds30-0280-moment-position-extended-protocol.md) · [Verified evidence](measurements/ds30-0280-moment-position-extended.json)

| Publication | Fixed error | Fitted error | Fixed conditional RF RMS | Fitted conditional RF RMS |
| --- | ---: | ---: | ---: | ---: |
| Official installed ALGO08v3, own full-20 ms observations | 1,743.35 m | 1,808.89 m | 98.74 Hz | 98.75 Hz |
| Ordinary successor, saved sparse observations | 1,336.71 m | 1,369.21 m | 137.92 Hz | 137.65 Hz |
| Moment-preserving correction, same saved sparse packet | 1,313.74 m | 1,343.01 m | 135.70 Hz | 135.41 Hz |

The independently held RF agreement gate rose from 513 to 516 among 541 matched observations at ±250 Hz and ±2 samples. The normal projected worker reproduced the exact candidate-only policy and applied 378 nonzero CFO edits among 558 admitted rows before Graph. No arrival, native winner identity or other measurement changed. The rebuilt Graph went from 5,649 assigned observations and 184 tracks to 5,622 and 183. Both runs used the lean route, one inference and the original late regional guard, which did not need an exterior probe. Both supplied all 179 grid points and eight verified PNGs. The satellite assignment was unchanged for all 4,721 common owners in each calibration arm. The correction dropped 152 owners, added 23 and changed 13 common residual roles. Position moved by 138.48 m at fixed `c` and 148.99 m with fitted `c`. All-owner RF RMS changed from 168.35 to 167.67 Hz and from 148.67 to 147.78 Hz, respectively. These RMS values include the ownership changes.

| Saved cell | Namespace launch to exit | Worker CPU to exit | Through verified publication wall / CPU | Post-publication residual export wall |
| --- | ---: | ---: | ---: | ---: |
| Ordinary | 22.176 s | 21.61 s | 21.735 / 21.213 s | 0.048 s |
| Moment-preserving correction | 27.151 s | 26.44 s | 26.600 / 26.054 s | 0.095 s |

The worker spent 2.587 wall s / 2.573 CPU s forming the projection, including 0.849 wall s for the masked forecast, 1.694 s for the unedited grouping Graph and 0.012 s for projection arithmetic. Paid solver time was 17.984 / 17.825 s wall / CPU ordinary and 22.692 / 22.596 s projected, inclusive of their actual Graph and feature work when enabled. Peak worker RSS was 1,114,952 KiB ordinary and 1,179,548 KiB projected. Worker CPU comes from in-namespace GNU `time`. The saved workers exclude raw acquisition and use the same already verified 47-body causal archive. The extended capsule hard-linked the existing staged bodies and native packets. It added zero archive bytes and performed zero original waveform or backing archive reads.

The live official driver logged no shared-lease deferral in either window. The next official storage deferrals appeared 8.722 s after ordinary lease release and 3.797 s after projected release. The latter launch began on a different new deferral, 40.774 s after ordinary release. The elapsed trigger-to-next-event interval was 32.053 s in each window, which includes the driver’s nominal 30-second sleep and its own admission work. The earlier 1.920 s mount failure and 21.002 s timeout remain separately recorded as infrastructure outcomes. [Earlier disposition](ds30-0280-moment-position-transfer.md)

This is one prospective held position result on the existing physical site. Its roughly five-second saved-worker cost is measured, and geographic generalization beyond this site and a whole-raw correction timing remain open.

## Reproduction

Use [the extended entry](ds30_0280_moment_position_extended.py) with the frozen installed interpreter, single-thread variables, CPU3 controller, nice 15 and idle I/O; the numerical child uses CPU2 and the ordinary shared lease. The commands are `prepare ROOT`, `watch ROOT --cell ordinary --pin READY --driver-pid PID`, `watch ROOT --cell corrected --pin READY --driver-pid PID --ordinary-gate-pin ORDINARY_GATE` and, only after both published cells seal, `score ROOT --pin CLOSURE`. The two existing lease receipts and the later official events are bound in the evidence. No numerical replay is needed to read the verified score. Seventeen component tests passed.
