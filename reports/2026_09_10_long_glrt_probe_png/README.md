# Individual GLRT probes: current 512 versus 8192 points

The three PNGs show the long candidate trajectories highlighted in the original
24-hour study. Every point is one 20 ms GLRT probe estimate. All 447 original
observations are present in both configurations; no failed or low-margin
estimates were removed for these plots.

| Candidate association | Span | Paired probes | PNG |
|---|---:|---:|---|
| STARLINK-32536 / NORAD 61925 | 64.0 s | 118 | [PNG](starlink-32536-512-vs-8192.png) |
| STARLINK-36469 / NORAD 67360 | 56.4 s | 207 | [PNG](starlink-36469-512-vs-8192.png) |
| STARLINK-30251 / NORAD 57532 | 49.2 s | 122 | [PNG](starlink-30251-512-vs-8192.png) |

Rows distinguish the original channel/edge/receiver tracklets. Separate rows
with the same receiver/edge identify separate time segments. The left and
middle columns show individual current and 8192-grid estimates with identical
axis limits for each row. They contain no temporal smoothing or fitted curves.

The right column magnifies the scatter by subtracting the **same baseline
cubic** from both configurations. That cubic has shared time coefficients and
one constant per original source tracklet; it is a display reference, not
ground truth. No cubic or orbital prediction enters either GLRT estimator.
All residuals are visible, with the same residual scale throughout each PNG.

Each probe uses its original independently acquired epoch/CFO seed.
Fractional timing is then refitted separately at 512 and 8192 points, so the
comparison includes the frequency grid's effect on timing refinement. The two
estimates share that probe's IQ and acquisition seed. Windows do not overlap
within a receiver; this does not assert statistical independence across
receivers, visits, or the paired configurations.

Frequencies use the original track's unwrapped alias branch and 11.2 GHz RF
normalization. The same original branch is used for both configurations.
Satellite associations remain unconfirmed; the 64-second arc is the previously
identified exploratory handoff candidate.

`paired-probes.csv` exports the paired plotted coordinates and common display
reference. `probes/` preserves each individual score, timing, acquisition seed,
sample window, source-manifest hash, and candidate ID. All current-grid raw
replays match published CFOs within 0.00001 Hz and margins within 0.00000001.
The replay checks that source windows never overlap within the same receiver.

Reproduce with `tools/plot_long_glrt_probes.py --source
reports/2026_09_10_scan_24h_glrt_rms --output <output-directory>` using the
scientific runtime with read access to the existing corpus and
`PYTHONPATH=src:tools`. Use `--render-only` to regenerate the figures from
the exported probe JSON. No recording or production configuration was changed.
