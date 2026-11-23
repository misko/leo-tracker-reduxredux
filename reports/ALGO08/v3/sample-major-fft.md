# Sample-interleaved FFT batches for independent receiver lanes

Batching two independent 12 ms lanes in sample-major order raised native FFT kernel CPU **41.5%**, even with layout preparation free. Including pack and unpack raised the measured scope **44.9%**. Four- and eight-lane batches were slower still. Every tested batched output transform changed Float32 bytes. The original scalar FFTs reproduced every captured output byte. This removes the tested layout from the legacy acquisition shortlist. [Sealed transform receipt](measurements/sample-major-fft.json.gz)

## Difference from the earlier stereo batch

The earlier `plan_many` trial handed FFTW two contiguous transform buffers from independent 20 ms antenna scouts. It preserved every factor and continuation state, while running 4.9% slower on weak and 7.2% slower on dense inputs than the matched scalar route. Its FFTW plan put a buffered wrapper around the original AVX kernels. This trial instead places the complex values of adjacent antenna calls together at each sample index. FFTW receives element stride B and transform distance one for B = 2, 4, or 8. Batches of four and eight can span independent consecutive visits. Readback restores the original lane and transform order. The 4,800-point lag FFT and the 4,096-point signed-CFO grid remain the same sizes. No phase, frequency, covariance entry, score or rotation is assigned from another lane. [Earlier contiguous stereo trial](stereo-fft.md) · [Layout and clocks](fft_lane_layout.c)

Both installed native libraries relinked byte for byte before the capture. The trace left the original receiver arithmetic in place and captured each FFT input and output. It preserved all **30 primary and 10 secondary** factors over 16 independent lane calls per aperture and all original per-recording continuation states. The captured panels include six lower-edge and two upper-edge stereo visits from the original weak archived windows. The archive was fully resident when the job checked it. Captured 20 ms residual scouts use the actual signed cancellation output. The 12 ms entry has no residual pass. No interleaved transform output entered scientific ranking or verification. [Trace and comparison](fft_lane_layout_trial.py)

## FFT boundary measurements

The standalone stock plan uses the installed aligned in-place `FFTW_ESTIMATE` geometry. Both layouts take the same captured Float32 inputs. Each repeats five times with the first arm alternating. Kernel clocks exclude copying. The charged clocks include arranging the layout from the original lane-major state, transforming it, and writing back in the original order. Planning runs outside both. The numbers below sum per-stage medians per complete captured sample. Each 12 ms batch width includes 128 lag forwards, 128 inverse lags and 384 carrier forwards.

| Captured scope | Batch width | Stock / interleaved kernel, ms | Stock / interleaved including layout, ms | Changed interleaved transforms |
|---|---:|---:|---:|---:|
| 12 ms primary | 2 | 2.82 / 3.99 | 4.72 / 6.83 | 640 / 640 |
| 12 ms primary | 4 | 2.80 / 4.37 | 5.07 / 8.10 | 640 / 640 |
| 12 ms primary | 8 | 2.84 / 7.49 | 5.22 / 11.78 | 640 / 640 |
| 20 ms raw | 2 | 2.83 / 4.01 | 4.84 / 7.43 | 640 / 640 |
| 20 ms signed residual | 2 | 2.83 / 4.02 | 4.93 / 7.40 | 640 / 640 |

The best interleaved 4,096-point kernel took **3.755 µs per transform** versus **3.746 µs** on the stock 12 ms plan. The 4,800-point forward and inverse kernels took **10.06 and 9.86 µs** interleaved versus **5.41 and 5.40 µs** stock. FFTW's interleaved plan selected a different radix and vector layout. The largest observed 12 ms raw deviations before the receiver's normalization were 9.16×10⁻⁵ on lag forward, 9.77×10⁻³ on lag inverse, and 3.05×10⁻⁵ on carrier forward. The test establishes a numerical difference at the transform boundary. It does not count changes to ranked carrier choices from this layout.

## Relation to the dense acquisition budget

The measured complete dense acquisition clock includes **12.635 CPU s** on 11,834 short calls and **4.716 CPU s** on 1,696 full calls. The first-four zero-wait model needs **3.49 s** removed there or elsewhere. The earlier unprofiled dense trace projects about **5.21 CPU s** for both broad search stages on short calls, including lag products, normalization, ranking and every carrier FFT. A short-only change would need to remove **67% of that entire stage** before any implementation overhead. The best observed interleaved kernel increased compute even before paying layout charges. The same comparison on 20 ms transforms showed a similar slowdown. The trial stopped at the measured transform boundary. [Dense split](dense-full-short-raw.md) · [Stage measurements](whole-group-receiver-bound.md) · [Current requirement](warm-recording-budget.md)

A covariance-first alternative has less measured leverage. The original packed frame planes already share each lane's normalized real and imaginary frame layout across covariance entries and both mode projections. Covariance is independently measured for both antennas. Charging the entire **169 µs** measured 14-frame mode stage to every 12 ms call, plus granting two such stages on every full anchor, gives **2.57 CPU s** for the whole dense recording. This is a deliberately generous clock-transfer estimate. The short path uses eight frame rows, and the measured full-aperture rate includes eigenvectors and projections, not just covariance. Independent stereo batching cannot remove the per-lane rows or the original eigenproblems. The earlier closure on FIR dead writes, template rotation sharing and timing pruning is separate from this estimate. A custom transform across lanes would need signed parity and a substantially different compute result to reopen this direction. [Released frame planes](../single-core-2x/receiver-frame-planes.md) · [Dense mode profile](receiver-polyphase-timing.md) · [FIR and loader ceiling](short-primary-dead-work.md) · [Rotation setup](short-shared-prep.md)

## Reproduce

One small native job verified archive residency and ran the synthetic layout tests and saved capture under the common Gauss lock. No dense waveform, position solver, or publication ran. Both owned tests passed. One checks stable batch grouping and the other measures independent synthetic tone bins with both FFT layouts.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
tree=/home/mouse9911/gits/leo-tracker-reduxredux
weak="$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip"
work=$(mktemp -d /dev/shm/leo-v3-fft-lanes.XXXXXX)
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env TMPDIR=/dev/shm OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$release/src:$release" timeout 65s bash -ec '
  read -r resident size < <(fincore --bytes --noheadings -o RES,SIZE "$3")
  ((resident >= size))
  "$1/venv/bin/python" -BPs -m reports.ALGO08.v3.fft_lane_layout_trial "$2" "$1/assets" "$3"
' sh "$release" "$work/native" "$weak" > "$work/receipt.json"
```

The sealed original receipt has uncompressed SHA-256 `7246950b055aff2323b4539208e0d7e45924e132d67a33880245dc77a77243d7`. It includes input I/Q identities, build digests, FFTW plan descriptions, exact comparison counts, creation cost and rotated clocks.
