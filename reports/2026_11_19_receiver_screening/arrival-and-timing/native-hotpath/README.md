# Typed detector hot path on contiguous saved IQ

The new C entry point runs the complete dual-receiver stock or fifth-center detector in one call. On 96 genuine windows from two roof captures, fifth-center median input-to-decoded-output wall time fell from **35.05 to 33.68 ms** and p95 from **43.73 to 42.68 ms**. The three roles agreed on every public detector field other than clocks and on all selected hints and region support. **Zero of 288 fifth-center repetitions per role met 20 ms**. [Stage chart](stage.png) · [PDF](stage.pdf) · [Timings](stage.csv)

The study fixed the first 24 chronological visits in segments 0 and 4 of DS26-0197 (lower) and DS29-0316 (upper). All prescribed IQ was valid. It matched **1,530 stock and 1,533 fifth-center ordered candidates**, including **306 and 315 gated candidates**, respectively. Those counts are across distinct windows, before timing repetitions. Six additional controls cover signed pilots at ±688.125 kHz, seeded noise and zero IQ on both edges. Both signed pilots survived on each receiver, noise and zero IQ yielded no gated candidates, and absent hints reproduced stock on all six controls. The scout can still propose epochs on noise before the detector gate. [Protocol](PROTOCOL.md) · [Input lock](source-lock.json) · [Pair receipts](measurements.json.gz)

## What changed

The standard three-lag proposal originally decodes each shared base time once and processes it with three delayed samples in a scalar loop on x86. The new loop batches four CI16 times in AVX2, extracts the selected receiver and shares its decoded base vector across all three lags. It retains each epoch's binary32 multiply, add and frame-accumulation order and uses the original scalar arithmetic on uneven tails. The existing ARM NEON and other fallback paths remain in source. This changes neither the GLRT preparation buffers nor the coarse, fine or fractional calculations.

The one-call interface owns the unchanged FFTW scout and detector plans. It consumes packed dual CI16 and writes existing typed rows into caller-owned storage. The fifth-center branch scans 26,666 score cells across both receivers for the highest eligible circular local maximum. It needs neither the sorted tail nor the later peak-separation tests. The exact ascending scan preserves the original score and lower-epoch tie rule. It also removes a 213,328-byte full-frame ranking scratch array relative to the typed sort control on this x86-64 build. The caller can omit the trace, which contains the chosen hints and detailed region support. The C path makes no Python or JSON calls.

## Same-core timing

All three roles ran three retained warm repetitions per genuine window in alternating order. Each recording used one fixed Intel Core Ultra 9 285K core. Each role had a separate loaded process, and the driver verified the exact detector library mapped by each typed role. The input-to-decoded boundary starts with already loaded contiguous CI16. It includes the native call and conversion of returned fields to Python values. Scheduled worker IPC, archive reads and diagnostic JSON serialization have separate or excluded clocks.

| Complete path, 288 calls each | Released ctypes p50 / p95 | Typed original kernels p50 / p95 | Typed hot path p50 / p95 |
| --- | ---: | ---: | ---: |
| Stock CPU, ms | 27.47 / 34.39 | 27.62 / 34.60 | 27.14 / 33.18 |
| Stock wall, ms | 27.63 / 35.27 | 27.99 / 36.81 | 27.38 / 35.14 |
| Fifth CPU, ms | 34.78 / 41.68 | 34.15 / 41.46 | 33.50 / 40.31 |
| Fifth wall, ms | 35.05 / 43.73 | 34.58 / 43.67 | 33.68 / 42.68 |

Median paired fifth-center wall savings were **1.24 ms** against the released ctypes call and **0.76 ms** against the same typed interface with original kernels and a full peak sort. The latter comparison isolates the two native changes. Stock met 20 ms on 0, 1 and 2 of 288 calls, respectively. [Complete distributions and paired differences](summary.json)

| Median CPU stage, ms | Typed original kernels | Typed hot path |
| --- | ---: | ---: |
| Stock IQ conversion and preparation | 3.594 | 3.618 |
| Fifth-center lag-44 FFTW score | 5.685 | 5.734 |
| Fifth-center scout rank | 0.449 | 0.042 |
| Ordinary three-lag fold in fifth mode | 1.236 | 1.019 |
| Fifth-center coarse CFO | 3.928 | 3.894 |
| Fifth-center fine FFT | 3.555 | 3.543 |
| Fifth-center fractional refinement | 9.181 | 9.167 |
| Fifth-center Python row decode | 0.248 | 0.250 |
| Separate diagnostic JSON encoding | 0.242 | 0.240 |

Per-lane scientific stages are summed inside a visit. Whole-call and nested stage medians are independent summaries. The complete typed fifth mode without Python decoding took 33.27 ms median CPU. Peak worker RSS ranged from 200,772 to 200,828 KiB for the typed original and 200,860 to 201,004 KiB for the hot path. These are Python worker process peaks and include imported libraries, template bindings and decoded diagnostics. The released comparison process held both separate detectors and reached 235,644 to 236,080 KiB. The candidate shows no measured RSS improvement against the same one-context typed comparator. [Per-stage clocks and memory](summary.json)

## Offline C release

The x86-64 Linux capsule contains the measured libraries, source closure, public headers, both edge template banks and one synthetic signed canary. It uses the system x86-64 glibc and `libfftw3.so.3`. The single-precision FFTW scout is linked into the typed library. The archive carries no authentic raw capture. A fresh extraction verified every packaged file hash and reproduced the published upper-edge canary for all three modes through the typed ABI and CLI. [Capsule](native-hotpath-linux-x86_64.tar.gz) · [Extraction and ELF verification](capsule-verification.json)

```sh
mkdir replay
tar -xzf native-hotpath-linux-x86_64.tar.gz -C replay
cd replay
sha256sum -c SHA256SUMS
timeout 10s ./native-hotpath fifth upper-strong.ci16 upper-exact.c16 \
  upper-control.c16 upper-filters.c8 upper-energy.f64 > receipt.json
```

Use `stock` or `absent` in the same command to test the other modes. Each IQ file has exactly 200,000 little-endian `[rx0 I, rx0 Q, rx1 I, rx1 Q]` signed 16-bit sample times at 10 MS/s. C callers include `source/native_hotpath.h`, create one context per edge and reuse `leo_native_glrt_result`. The library exports five `leo_native_hotpath_*_v1` functions. The existing detector ABI underneath keeps its full symbol list and public data layout. The archived source includes the original detector builder and the isolated SIMD overlay. The locked build receipts record the compiler, FFTW inputs, source digests and link commands. [Typed build](build.json) · [Detector build](detector-build.json) · [Result seal](result-lock.json)

The measured boundary is host RF detection from saved bytes. It includes no physical ARM behavior, acquisition, orbit fitting or position output.
