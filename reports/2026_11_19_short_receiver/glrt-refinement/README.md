# Fused post-coarse GLRT refinement

The fused bank reduced the combined integer and fractional GLRT CPU from 3.735 to 1.106 seconds across the valid holdout repeats, a 70.4% reduction. The full detector went from 23.414 to 20.334 CPU seconds, a 13.2% reduction. Both recordings met their individual 10% requirements. The pooled reduction fell short of the 15% material timing gate. All archived payloads were identical to the installed capture-era producer. [Protocol](PROTOCOL.md) · [Qualification summary](qualification.json)

## Profile and implementation

On one separate profiling visit per recording, the capture-era GLRT scoring calls consumed 0.39–0.45 s with the original fractional sampler and 0.25–0.30 s with the incumbent cached fractional sampler. The incumbent still allocated an integer IQ gather and corrected array for each frame, duplicated phase rows and the integer center in the five-cell timing grid, and built a 300-symbol workspace for each continuous 64-symbol score. The original acquisition's narrower CFO conditioning and coarse bank remained substantial separate costs.

The candidate fuses complex rotation and both 44-tap symbol correlations in one loop. On the 10 MS/s geometry, the 64 selected symbols form contiguous apertures. The candidate retains the capture-era absolute-phase calculation, the NumPy X86_V3 fused complex product order, and the four-lane pairwise reduction. It verifies the binary against NumPy's complex multiply and reduction before use and calls the original scorer for unsupported cases. All FFT transforms, tie rules, fractional grid cells, exact-versus-rolled contrast, and capture support are preserved.

Integer CFO rotations are shared across matching CFO rows. The center of the five-point grid uses the previously computed exact integer score for that receiver probe. The continuous phase vector retains the exact binary offset at each absolute sample. After subtracting the integer base index, all identical fractions use one normalized 16-tap Lanczos weight row. One fused interpolation and correlation pass forms both exact and rolled-control matrices. Across the holdout repeats, 1,830 integer cells were evaluated and 474 previously computed integer cells reused. The fused path's 231 continuous calls interpolated 9.59 million samples and required at most eight exact weight rows per call.

## Detector replay

Both modes used the same tiled coarse bank and incumbent cached sampler. Each valid visit had three paired repeats, with the order alternating by visit and repeat. Analysis used one numerical thread on CPU 12 for DS26 and CPU 13 for DS29. The two case processes ran concurrently on the same host. Timings are producer process CPU, excluding archive reads and compilation.

| Recording and split | Valid / scheduled | Median full CPU, control → fused | Total full CPU, control → fused | Full CPU saved |
| --- | ---: | ---: | ---: | ---: |
| [DS26-0036 development](DS26-0036-development.json.gz) | 4 / 4 | 0.973 → 0.867 s | 12.108 → 10.364 s | 14.4% |
| [DS26-0036 holdout](DS26-0036-holdout.json.gz) | 4 / 4 | 0.958 → 0.845 s | 12.864 → 11.366 s | 11.7% |
| [DS29-0082 development](DS29-0082-development.json.gz) | 3 / 4 | 1.064 → 0.865 s | 11.084 → 9.442 s | 14.8% |
| [DS29-0082 holdout](DS29-0082-holdout.json.gz) | 3 / 4 | 1.035 → 0.841 s | 10.549 → 8.969 s | 15.0% |

Holdout median wall time was 0.860 and 0.889 s per 20 ms RF visit. On one valid development visit per case, peak traced allocations changed from 21.50 to 24.68 MB on DS26 and from 22.31 to 24.74 MB on DS29. The largest listed fused-stage aperture arrays used 1.90 MB. These arrays exclude FFT scratch and cached geometry.

The two modes and original installed payloads agreed across all 16 scheduled archive visits, including both capture exclusions. All candidate ranks, scores, CFOs and fractional epochs matched exactly. The holdout had 15 integer and 14 fractional positives, all identical. The planted 731-sample, +48 kHz case recovered the correct epoch in both receiver lanes of both recordings, with fractional CFO error below 0.1 Hz. Empty IQ and the independent noise controls produced no positives. The synthetic full payloads were also identical.

## Partial-IQ position confirmation

The full no-repair v5 worker freshly fit one partial-IQ composite per recording. DS26 used eight fresh valid IQ visits and 6,757 archived valid visits. DS29 used six fresh valid IQ visits and 4,862 archived valid visits, and reproduced both sampled exclusions. The comparison reused the earlier fresh capture-era position controls on the exact authenticated full archives. The executed request hashes and native bytes matched their respective receipts, and the scientific settings matched between trial and control. All prepared observation, track, and final satellite ownership digests, both arm positions, RF scores, and conditional Doppler RMS were identical to capture-era controls. [Fused refinement positions](positions.jsonl.gz) · [Capture-era controls](control-positions.jsonl.gz)

| Recording | `c0` position error | Fitted-`c` position error | `c0` conditional Doppler RMS | Fitted-`c` conditional Doppler RMS | Fresh v5 CPU / wall |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0036 | 1.278365 km | 1.208143 km | 74.760916 Hz | 74.682298 Hz | 241.09 / 262.99 s |
| DS29-0082 | 0.566947 km | 0.517230 km | 97.003569 Hz | 96.683622 Hz | 162.25 / 190.85 s |

Each arm has two scored positions. The medians were 0.922656 km for `c0` and 0.862686 km for `fitted_c`, with interpolated 95th percentiles of 1.242794 and 1.173597 km. Full coordinates, RF scores, and prepared observation and track counts are in the position receipts. [Position-error distributions](error-distributions.json)

## Reproduction

Set the recorded producer first on `PYTHONPATH`, pin CPU 12 for DS26 or CPU 13 for DS29, and set `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `NUMEXPR_NUM_THREADS`, and `BLIS_NUM_THREADS` to one. Run `tools.pipeline_eval.qualification.refine_bank_eval` with the case ID, split and output path. Run `tools.pipeline_eval.qualification.refine_bank_position` with the corresponding case, report directory and a new work directory to reproduce the paired position check. Invoke the position module with `--package` on both completed position receipts.

The expanded position work for this run is under `/srv/bulk/leo-dev/refine-bank-position-20261119-pRoQKF`. The prior capture-era control receipts are under `reports/2026_11_19_position_atlas/spectral-grid`.
