# Pilot support and disjoint CPU in the guarded 12 ms primary

Only **one of 45 verified short primaries** used the same pilot interval in its scout confirmation and final verifier. Its entire early confirmation cost **17.7 µs**. The other 44 passed the first late check, which uses disjoint samples. Giving away the whole shared check projects **0.34 ms on North** and **2.37 ms on dense DS30-0008**. The full-rate refinement bank used the same 2,816-sample pilot region per frame as the final verifier, but all 45 winning bank requests changed frequency before verification and retained coarser statistics. The measured overlap is too small for a native fusion prototype. [Frozen protocol](short-primary-fusion-profile-protocol.md) · [Complete signed trace](measurements/short-primary-fusion-profile.json.gz)

## Complete native profile

The original first DS30-0169 member verified all 64 decoded window digests and admitted 51 stereo visits. The original schedule called the guarded short primary 86 times, with 45 factors and 41 empty calls. The other 16 antenna calls belong to the 20 ms schedule. The original member and index had all 19,295 pages resident before and after. Eight order-rotated repeats under the shared CPU2 lock compared the sealed guarded pack, a rebuild with the same source and no PGO, and its traced equivalent. The three arms produced identical ordered native factors and verifier audit bytes, timings aside. The sealed pack's factors matched the original signed archive on rank, integer and fractional time, and signed CFO within the experiment's score tolerance.

| Disjoint traced operation | CPU µs per short lane | Share of traced CPU |
|---|---:|---:|
| Carrier FFT grid, eligibility and row ranking | 261.1 | 23.1% |
| Eight-lag timing score and circular peaks | 170.8 | 15.1% |
| Four-request full-rate refinement bank | 169.7 | 15.0% |
| Input lane unpack and mix | 104.4 | 9.2% |
| Quarter-rate FIR | 86.1 | 7.6% |
| Independent early and late pilot confirmation | 70.8 | 6.3% |
| Fractional correlation including exact fallback | 69.9 | 6.2% |
| Frame modes | 65.9 | 5.8% |
| Integer verifier stencil | 62.9 | 5.6% |
| Verifier I/Q load | 49.7 | 4.4% |
| Fractional spectra and guard | 12.5 | 1.1% |
| Seed preparation, fractional vertex and other | 1.0 | 0.1% |
| Nonzero GLRT residual readout | 0.0 | 0.0% |

The complete signed lane averaged **993.6 µs sealed, 1,131.6 µs same-source rebuilt, and 1,128.6 µs traced**, using the median of eight batch means. The traced and untraced rebuild differed by 0.27%. The released build's 13.6% difference limits direct transfer of absolute substage times. The publication analysis instead normalizes the traced stage fractions to each archive's measured total short-call CPU. Median stage sums and whole-call median differ slightly. Positive lanes took 18.8 µs in pilot confirmation and 373.2 µs in verifier load, integer stencil and fractional work. Empty lanes took 128.0 µs in confirmation across rejected hypotheses and reached no final verifier. No verified lane selected a nonzero GLRT residual bin in this member. [Profile instrumentation and paired controls](short_primary_fusion_profile.py)

## What can share before the score grids

- The broad timing grid uses normalized lagged products of two adaptive quarter-rate modes. The carrier grid uses 704 filtered input positions per row and two independent mode FFTs. The final verifier needs the original 10 MS/s complex symbol products at a later signed frequency and fractional epoch. Decimation, eight-frame normalization, two-mode reduction and squared spectra discard data the verifier uses. This blocks reuse of the existing grid outputs as final pilot verification evidence. [Carrier grid and prior branch bounds](carrier-fft-bound.md) · [Integer timing trial](q15-timing-scout.md) · [Short timing and exact retry](precarrier-timing-gate.md)
- The 344 full-rate requests evaluate nine offsets with eight 352-sample blocks per frame. All 45 accepted verifier centers were within two samples of their actual winning bank seed. The bank changed CFO by **17.4–414.5 Hz** in absolute value, with a median **178.0 Hz**. Zero accepted CFOs matched any request on their lane. The bank stores eight-symbol block correlations and block energy. Even at identical frequency, two symbol sequences can have equal total correlation and energy in the block while placing their energy in different spectral bins. The verifier needs each 44-sample symbol, the rolled template and 16-tap fractional support. Preserving that evidence would require new per-symbol work inside the bank. The existing offset packing and convolution analysis already prices the unchanged bank. [Earlier pilot-bank measurements and arithmetic](pilot-bank-envelope.md) · [Signed refinement and gate bounds](refine-bound.md)
- The early scout and center of the integer verifier stencil can share an epoch, signed carrier and raw samples when the early check wins. The only such lane in this member used the existing float grouped check. The final verifier's double-precision symbol spectrum and normalization still use different reductions. The 44 first-late positives and all empty lanes lack a repeatable early-positive verifier pair. Granting the complete clock of the sole same-support early check already counts more than its reusable work.
- The integer verifier evaluates five adjacent exact-template shifts and holds four temporary symbol-correlation rows. The guard's fractional stage uses up to 16 adjacent source taps per sample, with weights selected from the actual rounded absolute source positions. Five integer scores cannot supply either the missing shifted correlations or the rolled template. Interpolation already serves both templates together. A broader per-symbol correlation bank would pay for additional shifts and exact numerical guards. The separate original-sample verifier load is the largest obvious remaining duplicate data pass. Even eliminating it entirely grants only **0.083 s North / 0.573 s dense**. Earlier trimming of this copy found no measurable gain. [Native stencil and interpolation context](pilot-bank-envelope.md) · [Measured load and FIR trimming](short-primary-dead-work.md)

## Optimistic publication limits

These scenarios weight the measured positive and empty stages by the archived counts and normalize them to actual short native CPU. North used **996 positives in 2,096 short calls, 2.043 CPU s**. Dense DS30-0008 used **6,380 in 11,834 short calls, 12.635 CPU s** in its earlier full-short build. Each row grants the indicated work for free, applies one-for-one wall-time credit and retains all other work. The rows are separate scenarios. [Reproducible projection](measurements/short-primary-fusion-price.json) · [North through-exit clocks](continued-cfo-north.md) · [Physical through-exit clocks](dense-full-short-raw.md)

| Removed short-primary work | North CPU saving (s) | North elapsed floor (s) | North speedup vs named | Dense CPU saving (s) | Dense elapsed floor (s) | Dense speedup vs named |
|---|---:|---:|---:|---:|---:|---:|
| Same-support early confirmation | 0.00034 | 11.224 | 1.493× | 0.00237 | 95.426 | 1.571× |
| All early and late confirmation | 0.140 | 11.085 | 1.512× | 0.773 | 94.656 | 1.583× |
| Entire full-rate bank and all confirmation | 0.451 | 10.773 | 1.556× | 2.672 | 92.756 | 1.616× |
| Entire timing and carrier search | 0.792 | 10.432 | 1.607× | 4.831 | 90.598 | 1.654× |
| Every short-primary operation | 2.043 | 9.181 | 1.826× | 12.635 | 82.793 | 1.810× |

The archived named denominators were **16.761 s North** and **149.886 s dense**. Their half-time targets were **8.380** and **74.943 s**. The historical dense candidate and named run had different input residency. The only new measurement is the resident DS30-0169 profile. On CPU alone the dense complete candidate would still use 54.716 s with every short call free, against 54.551 s for half of named.

## Reproduction

The profile binds the archived source and relink commands, each timed build, signed inputs, timing order, per-lane stage data and all native factors. Its uncompressed SHA-256 is `69613fd69b62395f285d153381bb2a57c07210eedf86f732173e9ad60508dca7`. Three component tests passed. With the import path below, run the offline projection against the sealed profile with `python -m reports.ALGO08.v3.short_primary_fusion_price PROFILE`. [Projection code](short_primary_fusion_price.py) · [Tests](../../../tests/pipeline_eval/test_short_primary_fusion_profile.py)

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -w 60 -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
  sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env \
  TMPDIR=/dev/shm OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$release/src:$release" \
  timeout 90s "$release/venv/bin/python" -Bsm reports.ALGO08.v3.short_primary_fusion_profile \
  /dev/shm/leo-v3-primary-pilot-fusion-reproduction
```
