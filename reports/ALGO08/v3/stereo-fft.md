# Independent stereo FFT batching on one core

The paired FFT path preserved the ordered native factor bytes and continuation state on all **66 authenticated stereo visits**. It cost **4.9% more native CPU on weak I/Q and 7.2% more on dense I/Q** than its same-build scalar path behind one dispatch. Against installed ALGO08v3 it cost 11.9% and 14.5% more. It left the 20% reduction screen unmet. [Frozen protocol](stereo-fft-protocol.md) · [Clocks, byte comparisons and FFT plans](measurements/stereo-fft.json)

## What could be paired

Installed ALGO08v3 runs each antenna's first scout, confirmation, pilot subtraction, second scout and original-I/Q verification on that antenna's own measurements. A close two-factor ordering can trigger the existing verifier retry inside the same antenna. The subsequent continuation keeps chronological history keyed by receiver, channel and exact RF. The older peer proposal and 22-anchor whole-detector retry experiments use separate policies. Neither the installed native cancellation entry nor its continuation requires the other antenna's measured factor to finish the current antenna. [Prior same-visit audit](../single-core-2x/receiver-lanes.md) · [Original native verification experiment](directed-verifier.md)

The earlier common-envelope sketch and partner-local detector transferred timing evidence between streams. The current implementation independently computes each antenna's input, FIR, frame modes, lag and carrier surfaces. It groups only the 4,800-point forward/backward timing and 4,096-point forward carrier transforms through `fftwf_plan_many_dft`. Separate scratch segments and both original I/Q lanes remain live. Each antenna resumes its own stock ranking and confirmation. If both lanes confirm, their independent signed cancellations feed a batched residual search. A single confirmed lane retains its scalar residual search. A single requested antenna uses the scalar dispatcher from the outset. [Timing implementation](stereo_fft_timing.inc) · [Per-lane routing](stereo_fft_pair.inc) · [Earlier envelope comparison](joint-envelope.md)

## Native cost and exactness

| Saved panel | Installed CPU s | Scalar, two local dispatches CPU s | Scalar, one local dispatch CPU s | Paired, one local dispatch CPU s |
|---|---:|---:|---:|---:|
| Weak, 18 stereo visits | 0.14045 | 0.14885 | 0.14981 | 0.15721 |
| Dense, 48 stereo visits | 0.25880 | 0.27879 | 0.27629 | 0.29622 |

Rows are medians of five repeat totals. Repeats alternated native call order and used one core and one FFTW numerical thread. Dispatch timing includes each native call through factor return. Original acquisition I/O and the subsequent continuation comparison were outside the clocks. Wall medians were 0.14049 versus 0.15724 s on weak and 0.25891 versus 0.29627 s on dense for installed versus paired. The one-dispatch scalar change is below 1% in median CPU in either direction across these panels.

| Panel | Batched primary visits | Batched residual visits | Visits with one scalar residual | Visits without a residual | Installed original primary / residual factors |
|---|---:|---:|---:|---:|---:|
| Weak | 18 | 18 | 0 | 0 | 36 / 22 |
| Dense | 48 | 20 | 12 | 16 | 52 / 28 |

The independently archived factor census binds to the same input hashes. Every local output kept those factors in byte-exact order, and every chronological continuation state and selection equaled installed v3. The native diagnostic used distinct arrays for both antennas and matched scalar output bytes for all three FFT directions/sizes. Both singleton masks produced the original lane bytes. Median singleton CPU on the original first six visits per cohort was 4.124 versus 4.422 ms weak and 3.615 versus 3.952 ms dense for installed versus paired wrapper. The wrapper's singleton path is the same unprofiled scalar implementation. Both original panels use centered mixers. [Saved measurement and singleton receipt](measurements/stereo-fft.json)

Each pilot edge's explicitly counted workspace grew from **10.880 MB** for the local scalar context to **21.838 MB** for the paired context. That bound excludes FFTW's opaque plan allocations. The paired constructor creates three additional batch plans and a second independent receiver context. Local constructor CPU ranged from 1.245–1.565 ms for scalar and 2.574–2.810 ms for paired, including allocation and plan creation. The visit wrapper makes no new explicit heap allocation or plan. Execution clocks include FFTW's internal work. [Constructor and workspace evidence](measurements/stereo-fft.json)

For both 4,800-point directions and the 4,096-point forward transform, the local FFTW planner placed a buffered wrapper around the two instances of the original per-transform AVX kernels. This is consistent with the combined path's extra work and byte parity. The measured latency combines the FFTW buffers and alternating two separate receiver workspaces. [Planner descriptions](measurements/stereo-fft.json)

The two local modified translation units were built with the archived arithmetic flags and without profile feedback. Unchanged linked objects and the original installed-bitwise relink provide the authentic comparison. Same-build scalar controls bracket the changed compilation before attributing the additional slowdown to batching. A prior profile on these exact input hashes assigns about **15.8% weak and 17.7% dense** of receiver CPU to the complete timing and carrier search stages, including ranking and associated array work. That is an approximate ceiling even when assigning those entire stages zero cost. The measured batch path leaves refinement, verification and each antenna's independent science in place. A custom fused kernel or a wider independent-lane redesign remains untested. [Matched previous stage profiles](measurements/receiver-polyphase-timing.json)

## Reproduction

Use the archived `receiver-fractional-exact-v1/build.json` link manifest and the installed v3 library. Under the exclusive one-core Gauss lock, run `stereo_fft_trial build ARCHIVE OUT/build INSTALLED`. Then run the two `measure OUT/build INSTALLED ASSETS WEAK BINDING BULK COHORT` invocations, with `weak` and `dense` as the cohort names. The dense binding is the original DS30-0008 signed prefix binding, and the weak archive is the original 18-visit satellite-reference archive. The raw reader uses the original read-only account and verifies old archive input digests. Two focused source and factor-wire tests passed. [Benchmark](stereo_fft_trial.py) · [Owned tests](../../../tests/pipeline_eval/test_stereo_fft_trial.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
benchmark=reports.ALGO08.v3.stereo_fft_trial
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD:$release/src:$release" OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 \
  OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs -m "$benchmark" "$@"
```
