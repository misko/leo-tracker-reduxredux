# Exact SIMD timing-mode rotations preserve factors and miss the CPU gate

On the first original DS30-0169 member, vectorizing the independent rows of each timing-mode eigensolver rotation saved **1.515 ms of isolated Jacobi CPU** with two 20 ms scans and **0.290 ms** on the active 20/8 ms schedule. All ordered native factors matched the respective shipped receiver byte for byte. Neither schedule cleared the 5% whole-callback CPU gate. Even making the entire Jacobi sweep free would save only **1.79%** and **0.84%**, respectively, of the profiled native CPU. [Frozen protocol](receiver-jacobi-columns-protocol.md) · [As-run receipt](measurements/receiver-jacobi-columns-0169.json)

## One verified member

The assay confined stock input to the first DS30-0169 member. Its 78,852,856 encoded and 102,400,000 decoded bytes matched the original manifest, index, original member digest and the previously verified ordered 64 window digests. All 19,297 source pages were resident. The 13 original exclusions left 51 stereo visits. The 20 ms scope exercised 102 lane calls and emitted 110 factors. The 20/8 ms scope exercised 16 original two-scan anchor calls and 86 short-primary calls, emitting 66 factors. Parity covers lane order, empty lanes, primary and residual records and all bytes returned by the native interface. The two schedules produced different evidence. No numerical localization or rendering ran. [Original input evidence](legacy-fresh-0169.md)

Both installed pilot files match their published pins. The runner itself binds and exercises the lower-edge pilot used by the member. The upper-edge digest was checked separately after the assay. Gauss used CPU 2, nice 15, I/O priority 7 and one numerical thread under the shared lock.

The scalar and vector switches share one rebuilt timing object per aperture. The vector code holds the eigenvector columns contiguously during the Jacobi sweep, then restores the original layout before mode projection. It keeps the original pivot and convergence arithmetic. An unsupported CPU or nonfinite covariance uses the original scalar path. This modifies neither the covariance construction nor the FFT timing and carrier search. The archived object recipes relinked both shipped references byte for byte, and the timed modified objects used no profile feedback. Timing probes were enabled only on separate passes.

| Native CPU, ms | 20 ms two scans | Active 20/8 ms |
| --- | ---: | ---: |
| Shipped, median of four ordered repeats | 291.501 | 125.199 |
| Rebuilt scalar, median | 311.511 | 139.596 |
| Rebuilt AVX2, median | 311.790 | 138.938 |
| Traced rebuilt scalar, complete callback | 316.617 | 140.074 |
| Traced rebuilt scalar, entire mode stage | 25.775 | 7.428 |
| Traced rebuilt scalar, Jacobi sweep within mode stage | 5.653 | 1.171 |
| Traced rebuilt AVX2, Jacobi sweep | 4.138 | 0.881 |

The AVX2 callback was between 1.43% faster and 2.10% slower than the same-build scalar callback on the full schedule, and between 1.57% faster and 1.30% slower on the mixed schedule. It used more CPU than shipped in every repeat on both schedules. The PGO difference prevents attributing that shipped-to-rebuilt gap to the SIMD implementation. The entire mode stage, including covariance and projection, accounts for 8.14% of the traced full callback and 5.30% of the traced mixed callback. The full scope recorded 162 scouts across 102 lanes, including 60 residual scouts. The mixed scope recorded 27 scouts on the 16 full lanes and 86 on the 86 short lanes. All repeat and stage clocks, including elapsed clocks, are retained in the receipt.

## What fits the pre-detection budget

The archived 100-process release budget gives a **2.35–2.44×** required speedup through detections if the complete post-detection interval improves **1.5×**. This scales case clocks uniformly and retains the failed cases in the original denominator. The bounds below transfer that requirement only as a diagnostic. They use three distinct measurement scopes.

1. **Resident DS30-0169 member, native and independent verification costs.** The shipped callback medians give a **2.328×** native speedup for switching apertures with different factor sets. The earlier independently verified stock pass took **171.075 ms wall and 171.063 ms CPU**. As a conditional serial CPU sum, adding that verification to each native median gives 462.564 and 296.262 ms, or **1.56×**. The modeled budget is 190–197 ms. Preserving the mixed callback CPU would leave 64–72 ms for all input verification, requiring roughly **2.4–2.7×** faster verification. Preserving verification CPU would leave 19–26 ms for all detector work, requiring roughly **4.9–6.8×** faster mixed callbacks. The sum excludes launch, receiver continuation, output sealing and any overlap. [Separate stock verification clock](measurements/legacy-fresh-0169.json)
2. **Resident physical DS30-0016, actual history-route acquisition.** The same 186 full lane calls and 1,240 short lane calls ran in the ordinary, fresh fused-map and prepared replay paths. Fresh fused-map acquisition spent **1.695 CPU s outside native callbacks**, including complete original verification. It then spent **0.478 s** on full anchors and **1.054 s** on short calls. Charging the earlier installed reference's 4.973 s after detections at 1.5× leaves **2.057 s** before detections for this case to halve its 10.745 s total. Even removing every short callback leaves **2.173 CPU s** of observed first-use work before startup and final detection-file overhead. Prepared replay lowers the corresponding modeled floor to **1.422 CPU s**, with prior verified map construction and reopening already paid. It measures a different starting state. [Actual first-use run](legacy-first-use-0016.md) · [Prepared replay](legacy-block-all-0016.md) · [Installed process boundaries](history-risk-physical-cohort.md)
3. **Cold physical DS30-0008, installed full receiver.** The earlier measured handoff took **99.528 s elapsed** and **58.961 CPU s**. It included 37.573 s elapsed and 37.338 CPU s of actual two-scan callbacks at 1.89% compressed residency. Applying the 2.35–2.44× target to this elapsed boundary leaves **40.790–42.352 s**. Holding the measured **61.955 s outside callbacks** fixed, even free callbacks leave **19.60–21.16 s** to remove elsewhere. The separately measured 21.623 CPU s outside callbacks also explains why a CPU-only model misses cold elapsed time. Input wait can change when compute and I/O are overlapped. [Cold and warm clocks](acquisition-split.md)

| Resident DS30-0016 history path | Acquisition elapsed, s | Full native CPU, s | 8 ms native CPU, s | Other acquisition CPU, s |
| --- | ---: | ---: | ---: | ---: |
| Ordinary verified input | 3.612 | 0.628 | 1.136 | 1.848 |
| Fused first use with full verification | 3.227 | 0.478 | 1.054 | 1.695 |
| Replay with prepared maps | 2.394 | 0.484 | 0.972 | 0.938 |

The measurements favor a change at both boundaries. For already recorded original frames, reducing cold wait or processing earlier during authentic reads has several seconds of room. The eligible fast replay already moves one benefit out of the fresh critical path by requiring a verified map in advance. Its fused producer eliminates a second traversal and still pays the whole original verification on first use. A prospective producer that can prove independently addressed raw extents at capture creates a different first-use verification boundary. That proposal requires a source contract and timing of the actual writer plus full reader verification. An original-frame proposal must still pay the original checksum and complete decoded digest evidence.

On the receiver side a substantive change must replace many paid timing and carrier searches, including the empty lanes, while leaving the original signed verification and both full anchor scans intact. The earlier four-row timing oracle projected **4.50 CPU s** of gross dense saving before discovering those rows. Available previous-visit and peer timing supplied every required row on **zero of 96** dense lanes. The four-frame 6.6444 ms alternative saved short CPU but lost strong 8 ms factors on both independently admitted members. FFT folding, lane layout and the symbol-sum kernel already have separate measured evidence. Together these observations leave several useful diagnostic budgets and no demonstrated path to a fresh 2× publication. [Timing oracle](timing-only-oracle.md) · [Shorter aperture](four-frame-primary.md) · [Polyphase FFT trial](receiver-polyphase-timing.md) · [Stereo FFT trial](stereo-fft.md) · [SIMD symbol sums](scout-gate-symbols.md)

## Reproduction

The existing member authority gate checks full tmpfs residency before opening the signed original member. Use the installed release and `receiver_jacobi_columns` with a fresh output directory and the same Gauss lock. The receipt records native source pins, compilation commands and the process settings. Its SHA-256 is `5a047e9230905a906723e594eef5477e2d89dde5e69eecf20e2baede3dc62b12`. The component tests use synthetic 5- and 14-frame rotations to verify byte equality of both updated arrays and the nonfinite fallback.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
  sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env \
  PYTHONPATH="$release/src:$PWD:$PWD/reports/ALGO08/v3:$release" \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.receiver_jacobi_columns "$new_tmpfs_output"
```
