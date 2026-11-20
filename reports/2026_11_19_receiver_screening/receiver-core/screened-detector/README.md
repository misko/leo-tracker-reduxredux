# Capture-era screened detector

Keep the installed screen as the default. Sharing a quantized template tap load across two adjacent epochs reduced the median screen-body CPU from 1,203 to 1,164 ms. The median matched complete-detector improvement was 0.05%. Bounded reuse of exact Lanczos coefficients removed 19 ms from the upper-edge interpolation leaf and improved matched complete-detector CPU by 0.41%. All variants preserved every public row and every recorded acquisition and screen decision. [Summary](summary.json)

## Full saved-IQ detector

Each authentic window included both receivers. The upper-edge recording DS29-0174 used its installed `a1b999a…` integer-VNNI screen, interval verification, exact sparse columns, and full fallback. DS26-0036 used its lower-edge `native-scope64-v2-3460060352b364a9` release with the original dense coarse path. The latter measures portability of the Lanczos change across producer generations. The VNNI adapter applies only to the screened release. Each panel used four sealed raw windows and three counterbalanced pairs per window. Four matched controls per panel used empty IQ, seeded noise, a weak pilot and a pilot at +720 kHz. All four real windows in each panel processed successfully, with 5–14 native candidates per window. No new IQ was collected. [Input and source lock](source-lock.json) · [VNNI lock](grid-source-lock.json)

| Producer and change | Whole warm CPU median, installed → candidate | Median paired CPU improvement | Median paired wall improvement | First-use CPU, installed → candidate |
| --- | ---: | ---: | ---: | ---: |
| Upper screened, reuse Lanczos weights | 1,723 → 1,717 ms | 0.41% | 0.30% | 1,228 → 1,260 ms |
| Upper screened, pair VNNI epochs | 2,371 → 2,304 ms | 0.05% | 0.71% | 2,345 → 2,297 ms |
| Lower legacy, reuse Lanczos weights | 3,194 → 3,006 ms | 2.92% | 3.04% | 4,176 → 3,990 ms |

The improvement columns use the median of the paired percentages, which preserves differences in raw window workload and execution drift. The algorithm panels use different authentic rosters. The old 0.756→0.818 s upper-edge FFT comparison used a third roster. Timing includes the installed full scan, row creation and probe projection after the saved IQ is loaded. A fresh process supplied each first-use timing after import and input authentication. Warm panels start after an installed scan initialized shared caches. Each Lanczos cache is rebuilt for each visit, with median setup under 0.1 ms. Loading the VNNI library took about 1.0 ms CPU and 1.1 ms wall. Compilation is offline. CPU 10 hosted both upper-edge variants and CPU 11 hosted the lower-edge panel. The controls are processed with one pair each and give no independent speed claim. [Previous FFT study](../../acquisition-support/capture-fft/README.md) · [Timings](summary.json)

## Where the upper-edge CPU went

| Installed stage on the Lanczos roster | Warm CPU median |
| --- | ---: |
| Detector/probe total | 1,723 ms |
| Complete acquisition | 1,489 ms |
| Screen and coarse selection inclusive | 1,068 ms |
| Integer-VNNI screen grid | 913 ms |
| Screen selection inclusive of exact columns | 109 ms |
| Exact columns | 19 ms |
| Normalized fine scores | 168 ms |
| Conditioned acquisition scores | 188 ms |
| Fractional GLRT | 211 ms |
| Five-cell integer batch inside fractional GLRT | 91 ms |
| Continuous conditioned score inside fractional GLRT | 123 ms |
| Lanczos sampling inside the continuous score | 64 ms |

Inclusive clocks nest, and their per-stage medians do not sum to a single capture. The measured trace key `screen_fp32_grid` was named before the installed backend reported `integer_vnni`. The summary uses the observed backend name. The existing lower-edge Lanczos scorer benefited more from the same implementation, with a 151→29 ms leaf median. On the screened release, the incumbent already handles a uniform fractional offset with one Lanczos row. The new route retains per-sample multiplication and reduction order, reuses rows across calls and groups nonuniform positions by the exact binary64 phase. Across the 12 upper warm pairs it interpolated 6.79 million samples using 591 computed coefficient rows, with 2,286 of 2,430 calls on uniform offsets. Its 512-row cache holds at most 64 KiB of weights plus bookkeeping. Larger calls and irregular phase sets use the original sampler. [Upper-edge observations](DS29-0174.json.gz) · [Lower-edge observations](DS26-0036.json.gz)

The VNNI library keeps the installed integer quantization, normalization, and sum order. Two adjacent epoch accumulators share the same packed reference load. A 21-CFO call still occupies all three eight-lane groups. The work remains the full direct correlation over those cells. The audit checked all 4,759,881 screen cells across 17 activated screen calls, including 3,079,923 authentic cells, with zero differences and zero replacement fallbacks. Empty IQ bypassed the screen naturally. The outer scanner retained the original exact-column verification and refinement in every call. Dividing the screen into two-epoch blocks reduced loads, while leaving the count of VNNI dot instructions unchanged. The small measured effect does not warrant changing the default. Native temporary buffers are bounded to 3.35 MiB per tile, excluding NumPy inputs and returned rows. No ARM measurements were taken for these host runs. [Complete VNNI trace](grid-run.json.gz)

## Native input to localization

For each panel, the installed and candidate projected probe pairs were byte-identical to each other and matched the original frozen capture-era probes. Replacing the four pairs in each complete factor document left the complete ordered probe array identical, including the untouched 6,761 or 6,700 visits. This is a partial-IQ identity check at the input to both calibration arms. The study reports detector timings and factors without a new position solve or performance claim beyond that boundary. [Factor identity receipts](factor-parity.json)

## Opt-in and reproduction

In a dedicated single-detector process, use `tools.pipeline_eval.variants.screened_detector.route()` around the installed `scan_capture_window()` for Lanczos reuse. The x86-only alternative is `screened_detector_grid.Grid(screened_detector_grid.build(path)).route()` around that call, using an absolute local scratch library path and the bound integer-VNNI producer on `PYTHONPATH`. `Grid` requires AVX-VNNI, AVX2 and FMA. Unsupported input geometries retain the original grid. The contexts restore the installed function on exit. The trial workers record the same stock policy and validate source and IQ hashes before replay.

With the repository and source root on `PYTHONPATH`, the installed `/opt/leo-fast-auto/20261010-r1/venv/bin/python`, one BLAS thread and single-core `taskset`, run `python -m tools.pipeline_eval.qualification.screened_detector_trial freeze <scratch>` and then call the same module with the recording ID and scratch directory. Add `--cold installed` or `--cold reuse` for separately launched first-use workers. The grid study uses `python -m tools.pipeline_eval.qualification.screened_detector_grid_trial freeze <grid-scratch>`, then `installed`, `vnni_pair`, and `run` in separate calls against that directory with the screened source root. Consolidate the traces and use `python -m tools.pipeline_eval.qualification.screened_detector_results <report-dir>` to recheck full scientific equality, derive paired statistics and recheck the complete factor arrays. [Artifact hashes](SHA256SUMS)
