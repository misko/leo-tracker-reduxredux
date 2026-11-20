# Batch neighboring fractional samples in the wide detector

The candidate reproduced the released wide detector's complete output on **30/30** authentic dual-RX visits. Median fractional GLRT CPU fell from **6.14 to 5.54 ms**. The complete detector met the **20 ms wall deadline on 245/270 calls**, up from **234/270**. The wall-time 95th percentile rose from 21.89 to 22.19 ms. These are host measurements on a bounded panel. [Stage chart PNG](wide-kernel.png) · [PDF](wide-kernel.pdf) · [Paired timings](timing.csv) · [Detailed results](qualification.json)

## What changed

The candidate keeps all four time regions, the 21 coarse CFO bins spanning ±800 kHz, both templates, the full fine search and all gates. It changes only interpolation inside fractional GLRT. When consecutive sample positions use the same binary64 Lanczos row, an AVX2 block evaluates four adjacent outputs at a time. Each output still accumulates all 16 taps in their original order and uses the original division. Binade crossings, unsupported CPUs and paths outside the wide short-window mode use the installed scalar path. The added temporary is a bounded 1 KiB sample block.

The measured work is distinct from coarse CFO striding. The trace build processed 11,288,112 fractional samples in the vector path and 20,944 at rounding boundaries over one untimed replay of each of the 30 visits. It executed 90,640,000 ordered tap-vector multiplications from the original 180,944,896, because each AVX2 multiply carries two independent complex outputs. Every output still has the same scalar arithmetic and precision. The production build excludes counters. Trace outputs matched the production candidate on all measured visits and controls. [Earlier CFO stride](../../receiver-core/cfo-stride/README.md) · [Trace build](trace-receipt.json)

## Saved-IQ timing and payload parity

The panel scheduled 32 visits and retained two pre-existing invalid DS29-0082 visits as exclusions. The 22 admissible held visits came from the frozen two-band stride panel. Eight additional visits were the highest two prior CPU observations per recording from four complete canonical-wide replays. Archived whole-service control CPU for those visits ranged from 24.95 to 44.45 ms. Replaying the same visits in the warm harness produced lower medians, so the tail selection identifies hard prior observations under their original host conditions. Each processed visit had nine counterbalanced matched repeats on CPU 0 at nice 10. Input and output identity checks stayed outside timed calls. [Input and source lock](source-lock.json)

| Boundary, all 270 calls per detector | Released wide | Batched fractional |
| --- | ---: | ---: |
| Median native detector CPU | 15.342 ms | 15.073 ms |
| Median wrapper CPU | 15.612 ms | 15.335 ms |
| Median wrapper wall | 15.651 ms | 15.518 ms |
| Median fractional GLRT CPU | 6.137 ms | 5.540 ms |
| Median proposal CPU | 1.425 ms | 1.434 ms |
| Median coarse grid CPU | 1.864 ms | 1.886 ms |
| Median fine FFT CPU | 1.664 ms | 1.658 ms |
| Native CPU ≤20 ms | 255/270 | 262/270 |
| Wrapper CPU ≤20 ms | 247/270 | 259/270 |
| Wrapper wall ≤20 ms | 234/270 | 245/270 |

The median paired native-detector improvement was **0.404 ms (2.47%)**. The fractional phase had a 0.525 ms median paired improvement. Phase medians do not sum to the complete detector median. The complete timed boundary begins with already-loaded contiguous CI16 and ends with decoded public detector rows. In the 22 held visits, wall deadlines were 190/198 for both libraries. For the eight prior CPU-tail visits, they improved from 44/72 to 55/72. Their wall p95 increased from 23.04 to 33.33 ms. This shows a higher observed deadline fraction, with remaining latency tails. The data report Intel x86 host behavior. [270 paired repetitions](timing.csv)

All 480 authentic nonclock candidate records, including their order and the 132 gate positives, matched exact public bytes. The baseline matched the archived detector payloads or the archived full-waveform probe projection. On each sideband, the two receivers found the weak +479.875 kHz plant and the signed ±799.875 kHz plants with the same payload in both libraries. Both libraries produced zero gate positives on both empty and both seeded Gaussian controls. The stock and candidate CLI also agreed on both authenticated band fixtures under QEMU's Nehalem model with AVX2 disabled. That test measures scalar-fallback parity. [Lower-band receipt](DS26-0036.json.gz) · [Upper-band receipt](DS29-0082.json.gz) · [Scalar fallback receipt](scalar-fallback.json)

The detector chart ends with the public factors. Complete saved-IQ services through both position arms have their own study. The initial replay stopped at an archive chunk whose selected visit required more than 48 MiB of decoded prefix. The final harness used a bounded 128 MiB prefix budget for one selected visit. The earlier source freeze preserves proof that the input roster, C binaries and protocol were identical before and after that reader adjustment. [Preflight source lock](preflight-source-lock.json)

## Release and reproduction

The production ABI-1 library exports the same entrypoints and uses the original build recipe. Its SHA-256 is `758a0ccc4b61c4c8cc7fc96c23ea34bfea38eeb6e7c34cc225f28129cefae2d3`. The worker can load the candidate as an ordinary native library with the same four-center wide release settings. [Release receipt](release.json) · [Native build receipt](build-receipt.json) · [Evidence hashes](evidence-lock.json)

The chart and CSV can be regenerated from the stored receipts without raw IQ or native binaries.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.wide_kernel_results \
  --out /var/tmp/leo-wide-kernel-offline
```

Build a fresh candidate from the verified local wide source with `python -m tools.pipeline_eval.qualification.wide_kernel_build --work <local-scratch>/release`. Use the same invocation with `--trace` and `<local-scratch>/trace` for the operation-count build. The replay driver checks both artifacts and enforces the frozen IQ digests. The fallback driver uses the existing native CLI with `qemu-x86_64 -cpu Nehalem-v1`.
