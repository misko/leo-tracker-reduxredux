# Lower precision, packed data and compiler tuning on PLUTO+

## Outcome

Genuine packed Q15 FFTs reduced floating-point work but made this Cortex-A9
search substantially slower. Packing FP32 FFT outputs into scaled Q15 halved
the spectrum payload; even NEON packing did not beat the FP32 baseline.
Compiler/local-arithmetic tuning was the useful direction. These are research
prototypes; production analysis is unchanged.

The experiment retains raw FP32 fine FFTs without fine-FFT FP64 fallback.
The separate residual-boundary conditioned fallback remains enabled and the
final GLRT uses FP64. No windows or candidate entries were pruned here.

## ARM timing

Timing is CPU0 on PLUTO+ 192.168.1.15, four saved 120 ms dual-receiver dwells
at 2.5 MS/s: 88 receiver-specific 20 ms windows and 704 candidate entries.
Every listed method recovers **119/119 standard positive hits**, with 139
unmatched positives. This small ARM panel is distinct from the larger host
quality checks below. Search time includes inner per-window ingest, scaling,
packing, peak buffers and fine-cache work. It excludes workspace and template
allocation, initial FFT plan setup, the outer probe's CI16-to-FP64 window
conversion, proposal-region construction, file loading, proposals and
simultaneous capture. The outer
conversion exclusion was clarified by the later fused-timer experiment in
`../2026_09_29_arm_subsecond/WAVE2.md`; the recorded stage times are unchanged.

| Method | Search CPU seconds/dwell | Interpretation |
|---|---:|---|
| Raw FP32 reference, fresh run | 4.863 | Comparison baseline |
| LTO, no math errno/traps, otherwise strict FP | 4.879 | No speed benefit |
| Local arithmetic + LTO + limited complex range, corrected v2 | **4.468** | **8.1% less search CPU; 1.088x speedup** |
| Packed Q15 integer FFT, ARM dual-halfword DSP | 20.357 | 4.19 times slower |
| FP32 FFT with scalar packed-Q15 spectrum cache | 6.505 | Slower despite smaller cache |
| FP32 FFT with NEON packed-Q15 spectrum cache | 5.168 | 6.3% slower than raw FP32 |

The corrected compiler variant took 4.464381 and 4.471259 seconds/dwell;
the table uses their mean. Adding the previously measured 0.851639-second
proposal stage gives **5.319459 seconds/dwell**, a separately measured stage
sum, not a fused benchmark. That is still 44.3 times the 120 ms real-time
budget and 73.9 times the 72 ms budget for 40% headroom. Higher-rate ARM
timings and concurrent capture-to-RAM qualification remain open.

Use corrected `limited-complex-v2` as the fastest measured experimental
extension to raw FP32 for this finite-data workload; retain the strict raw
FP32 executable as the comparison reference. Do not adopt Q15 for speed on
the strength of these implementations. The useful saving is reduced complex
arithmetic overhead, not reduced FFT precision or a measured FLOP-rate claim.

Exploratory v1 local-arithmetic/combined/limited-complex runs took 4.717,
4.756 and 4.483 seconds respectively. A target unit test then exposed an
alignment assumption: FFTW's target allocator did not guarantee 16-byte
alignment. These v1 runs are preliminary, not qualified implementations.
V2 uses explicit `posix_memalign(16)` and matching `free`, preserves the
alignment test, and reruns both ARM tests and the selected timing workload.

## What was tried

- **Compiler tuning:** LTO, `-fno-math-errno`, `-fno-trapping-math`, explicit
  complex arithmetic, reciprocal normalization, restricted pointers, aligned
  cache storage, and `-fcx-limited-range`. The original build already used
  `-O3`, Cortex-A9/NEON and hard-float targeting. No global fast-math was used.
- **Actual integer FFT:** packed pairs of signed 16-bit lanes, exact mixed-radix
  2/3/5 transforms of 5,000/10,000/15,000/20,000 points, dynamic input scaling,
  per-stage scaling, widened accumulation and ARM `SMUSD`/`SMUADX` multiplies.
  Preplanned stages and constant divisions remove software division from the
  transform. No power-of-two grid substitution; zero observed clipping.
- **Packed cache:** FP32 FFT remains; only its stored spectrum becomes two
  Q15 lanes plus a per-frame scale. NEON peak scanning and packing replace
  the scalar conversion loop. Scored bins are dequantized as needed.

NEON reduces packing CPU from 1.587 to 0.382 seconds/dwell (4.16 times faster),
and scale scanning from 0.208 to 0.066 seconds. Dequantization still costs
0.174 seconds/dwell. Total packed-search CPU falls 20.6%, but conversion work
still exceeds the benefit of smaller storage. The payload is approximately
halved; peak resident memory was not measured. This is not an integer FFT.
The packed-cache clamp counter measures pre-round endpoint clamps, including
small reciprocal-rounding overshoots; it is not a count of lost Q15 levels.

`-fcx-limited-range` changes exceptional complex-number behavior throughout
the executable, despite unchanged final-GLRT source. Qualification covers
finite saved CI16/template workloads, not NaN, infinity, overflow, signed-zero
or floating-point exception equivalence. These flags are not an unconditional
production default. This was a bounded set of relevant tricks, not every
possible compiler configuration; PGO and a specialized integer NEON FFT remain
unmeasured.

## Recovery against standard analysis

All small-panel methods recover **838/843** standard detections on 32 mixed-rate
DS7 dwells (704 windows, 5,632 candidate entries), matching raw FP32 recovery.
There are 884 unmatched positive entries. That panel alone does not justify a
large-cohort quality claim for the rejected integer/packed variants.

The corrected compiler variant was actually executed on **704 dwells from
88 DS7 recordings**, with **15,488 windows and 123,904 candidate entries**.
It recovers **19,400/19,581 standard detections (99.08%)**, the same count as
the selected raw-FP32 restricted-search baseline. This is not every DS7 dwell.

| Sample rate | Standard hits recovered | Unmatched positive entries |
|---|---:|---:|
| 2.5 MS/s | 4,551/4,573 | 4,387 |
| 5 MS/s | 5,420/5,466 | 4,931 |
| 7.5 MS/s | 5,137/5,186 | 4,758 |
| 10 MS/s | 4,292/4,356 | 4,252 |
| Total | 19,400/19,581 | 18,328 |

Compared with raw FP32, zero candidate positive decisions, coarse candidates
or per-window recovery counts changed. Maximum margin difference was
1.62e-9; maximum CFO difference was 0.000655 Hz. Corrected v2 candidate
objects were identical to the v1 compiler variant on this complete panel.
The 18,328 unmatched positives remain a material quality limitation; retained
original hits do not establish equivalent output or independently verified
physical detections. DS8/DS9 were not rerun for this compiler experiment.

Matching uses the sealed standard-pipeline baseline, same receiver/window,
maximum-cardinality one-to-one matches, margin >=0.025, epoch distance <=2
samples and tracking CFO distance <=8 kHz. Candidate entries and actual GLRT
kernel calls differ because conditioned fallback can score again; exact call
counts are in `results.json`.

## Evidence and reproduction

- `PROTOCOL.md`, `evaluate.py`, `test_evaluate.py`: frozen workload and runner.
- `results.json`: timings, hit counts, per-rate counts, actual GLRT calls and
  input audit hashes for each completed cohort.
- Each cohort's `manifest.json`, `summary.json`, `standard-audit.json`, and
  `build-receipt.json`: binary, source, input and output hashes. Full row files
  stay in the local experiment workspace; published summaries retain their hashes.
- `host704-limited-v2/precision-comparison.json`: comparison with raw FP32.
- `arm-units.json`: all seven freshly built component test executables passed
  on the physical ARM. Host/sanitizer tests cover all four rates and partial
  frames. Fixed FFT tests include direct-DFT bins and extreme integer lanes;
  packing tests cover rounding ties, endpoints and randomized scalar parity.
- Adjacent `arm_compile_pack`, `arm_fixed_fft`, `arm_packed_cache` directories
  contain build tools, component tests and archived source/build provenance.

Run `evaluate.py --help` for binary/receipt/reference selection. ARM jobs must
run serially. The standard matcher is the existing fine-precision `audit.py`;
`summarize.py` verifies local rows and receipts before collecting results.
No RF, capture, storage formatting or service configuration was changed.
