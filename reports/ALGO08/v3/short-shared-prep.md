# Sharing coarse template setup across short receiver calls

The 12 ms receiver rebuilds one pilot rotation for each distinct coarse CFO in a lane's refinement bank. A standalone timing of the archived routine costs **5.151–5.152 µs** per rotation on the two pinned pilot edges. Granting four free preparations on all **11,834** short calls would remove **0.244 CPU s** at that measured rate, against **12.800 s** needed for half of the historical dense total CPU. Exact caching has no measured route to a large saving. [Frozen protocol](short-shared-prep-protocol.md) · [Measured receipt](measurements/short-shared-prep.json)

## What the installed callback already shares

The full-coverage callback opens one full and one shortened context per active pilot edge. Each context serves both antennas and all RF streams throughout the acquisition. It loads and validates the pilot, prepares its quarter-rate timing templates, lag filters, transform tables and FFT plans once. The verifier already retains the exact and rolled GLRT templates, weights, FFT workspaces and a last-exact-CFO integer rotation within the context. The carrier-eligibility cache also retains the exact sample rate and signed frequency interval and center, across calls. Previous mixed setup measured **2.564 ms on lower and 2.417 ms on upper** per edge including library and asset preparation. The weak and dense archived seed panels both used zero mixer center, where there is no per-sample RF-center rotation to share. [Native callback](mixed_aperture_receiver.py) · [Original setup clocks](mixed-aperture-receiver.md) · [Carrier eligibility](../../../tools/pipeline_eval/variants/experimental/receiver_carrier_eligibility.inc)

The short path chooses four coarse timing and frequency requests per lane. The 1.6 MHz search interval is narrower than the 2.5 MHz decimated sample rate, so each request has at most one signed branch. The existing bank already groups bit-identical coarse frequencies *within* a lane. Its 2,816-tap rotation and pilot energy depend only on the fixed pilot coefficients and exact coarse CFO. They do not depend on antenna or epoch. A persistent cache could reuse these across visits for one pinned pilot and floating-point mode. A 64-entry bank is **1.44 MB** per edge, before table overhead. Immutable pilot energy can also be hoisted without retaining a bank. This is part of the cost already priced below. [Existing refinement bank](../../../tools/pipeline_eval/variants/experimental/receiver_refine_batch.inc)

The correlations, epoch scores, carrier refinement, independent scout confirmation and verifier still depend on each lane's waveform. Reusing a full verifier result for the same RF would bypass that independent evidence. Exact downstream oscillator memoization needs the refined frequency bits and, for the fractional calculation, its time geometry. The saved original 20 ms primary trace has **52 of 52** distinct scout-confirmed refined CFOs on dense and **36 of 36** on weak. Fractional verifier timing and carrier interpolation therefore remain outside this sharing estimate. [Signed scout rows](measurements/scout-readout.json.gz) · [Earlier absolute-phase preparation measurements](../single-core-2x/receiver-absolute-phase-avx.md) · [Existing adjacent-epoch stencil sharing](../single-core-2x/receiver-stencil.md)

## Exact-key recurrence and cost

Archived primary seeds were joined by original visit, antenna and signed decoded I/Q digest to the pilot-edge records. The keys are the complete coarse-CFO bits, counted after the already present within-lane grouping and wrap exclusions. The counts capture both within-stereo and across-visit recurrence in input order. These are original **20 ms v3** seeds. The 12 ms receiver uses the same coarse CFO grid and can make different selections. Its hit rate remains unmeasured.

| Signed primary trace | Lanes | Existing rotation preparations | 16-entry hits | 64-entry hits | Unbounded hits |
|---|---:|---:|---:|---:|---:|
| Dense DS30-0008 prefix | 96 | 384 | 0 | 10 | 37 |
| Weak DS26 archived clips | 36 | 144 | 0 | 1 | 1 |

The native cost gate extracts only the verified 12 ms C rotation and energy routine, compiles it with the archived non-PGO floating-point and optimization flags, and times it in four rotating output slots. It uses 347 zero-centered coarse bins from the signed dense seed trace and the shipped pilot assets. Each of five repeats prepares the bin list 32 times per edge. The median was **5.151 µs lower / 5.152 µs upper**, including the benchmark loop and output observation. Both signed edge assets gave bit-identical pilot energy at the two tested extreme bins, while their rotated values differed. No complete receiver code, waveform acquisition or positioning ran for this measurement.

The **0.244 s** projection gives every dense short call all four setup slots for free, with no lookups, memory pressure or misses. It is a generous transferred stage cost from a standalone routine, without the shipping object's profile layout or full receiver cache traffic. The actual dense candidate used **12.635 CPU s** in all short calls. If the old dense 64-entry hit rate transferred, even free hits would save about **6 ms** across the complete recording. The shared template ceiling is too small to justify building a new detector. [Actual raw native and publication clocks](dense-full-short-raw.md) · [Audit program](short_shared_prep.py)

## Reproduce

The receipt binds the actual short binary, C source fragment, pilot assets and original archives. Two component tests passed, covering bit-identical signed zero keys, repeated in-lane frequencies, wrap eligibility and per-edge LRU behavior.

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
short=/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so
source=/var/tmp/leo-short-signed-02/short/delay_product_kernel.c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD:$release/src:$release" PYTHONDONTWRITEBYTECODE=1 \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.short_shared_prep \
  "$source" "$short" "$release/assets" "$fresh_output"
```
