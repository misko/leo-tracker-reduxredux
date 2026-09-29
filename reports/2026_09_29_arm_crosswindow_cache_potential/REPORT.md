# Across-window final-GLRT frame-cache potential

This is a read-only key-collision estimate over fused-V4 `host704-v4` rows. It
uses only the 123,904 visible final candidate results. Initial GLRT calls made
before a boundary fallback are absent from the rows and are excluded.

For every visible candidate, the key is receiver, rate, absolute frame start
`window*Fs/100 + refined_epoch + nearbyint(frame*Fs/750)`, the early/late
64-symbol region, and CFO. A candidate-level `(refined_epoch, exact CFO)`
deduplication is applied within each receiver/window before measuring
across-window frame reuse. That removes 16,704 visible calls, leaving 107,200
calls and 1,702,253 usable frame evaluations.

The frozen V4 build leaves `LEO_PRESENCE_GLRT_SYMBOL_DIVERSITY` at zero, so
all observed final frames use the early region. The analysis still applies the
`glrt()` terminal-frame rule: a late frame that crosses the dwell end switches
to early before its support check. Partial terminal frames reduce the frame
denominator below 16 per call.

| CFO key hypothesis | cross-window frame hits | share of frame evaluations |
| --- | ---: | ---: |
| exact IEEE-754 acquired CFO | 533 | 0.0313% |
| rounded to 100 Hz | 33,883 | 1.9905% |
| rounded to 500 Hz | 60,838 | 3.5740% |
| rounded to 1,000 Hz | 68,864 | 4.0455% |

At the 1 kHz hypothesis, rates 2.5/5/7.5/10 Msps contribute respectively
4.93%, 3.60%, 4.31%, and 3.52% cross-window frame hits. Exact-CFO reuse is
negligible, while even the unvalidated 1 kHz quantization only exposes about
four percent of the modeled frame work. This is a collision estimate only; it
does not validate CFO quantization, establish a cache implementation, or make
speed or quality claims.

Machine-readable counts and key geometry are in `potential.json`.
