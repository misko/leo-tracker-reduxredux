# Support shared by raw and signed residual scouting

After signed cancellation, **91 of 92** measured residual scans had exactly **200 of 50,000 quarter-rate FIR outputs** whose full native input was unchanged. The remaining scan had 228. The sample includes 38 exported second carriers, each with 200 reusable FIR outputs. **Every one of the 1,288 covariance rows intersected changed samples.** The measured support gives a generous budget below **0.3% of native CPU** for exact input and FIR reuse. [Per-lane support and timing receipt](receiver-cancel-support-results.json)

## Cancellation and receptive fields

The frozen receiver copies its interleaved CI16 input, fits a complex coefficient in each pilot block, and applies signed subtraction, rounding and clipping on the selected antenna. Its symbol support runs from symbol 2 through 301, covering 13,200 samples in each 40,000-thirds-of-a-sample frame. Partial frames at the ends are clipped to the actual recording. The resulting guard interval is 133–134 samples. Removing the 40 native samples on either side of a quarter-rate FIR center leaves 53–54 candidate centers in each guard interval. Mapping those centers to the actual stride-four sample grid gives 200 complete FIR stencils across the 20 ms window.

The first and second scouts use the same absolute sample origin and mixing center. An entirely unchanged stencil can therefore reuse the first output at the same position. The audit compares both signed CI16 components at every native index after quantization and clipping. It counts actual unchanged runs, including zeros introduced by quantization. All 12 residue classes of the confirmed phase on the FIR grid in thirds of a sample occur in the saved lanes. Those visits have zero metadata mixing center. Nonzero centers use the same deterministic input rotation in both scouts, but the first scout reloads unrotated samples for fine refinement. Retaining a rotated input would cost another buffer or more computation.

The covariance stage centers and normalizes 14 overlapping rows. Each row spans 4,740 quarter-rate samples and depends on its complete input. Exact reuse of a covariance entry requires both contributing rows to be unchanged. The two principal modes mix all 14 rows, so the clean FIR intervals do not supply reusable complete timing or carrier FFT inputs. An update through a different subtraction or reduction would require a separate numerical comparison. This audit measures byte identity before the existing numerical kernels.

Earlier work already proposed fusing cancellation into the next search to save the raw copy. The linear projection trial used an actual signed correction to update a different scout through linearity. These studies did not measure equality of the frozen nonlinear scout's input support. [Earlier receiver directions](../single-core-directions.md) · [Linear projection comparison](receiver-projection.md)

| Saved slice | Lanes / residual scans / exported residual factors | Mean unchanged native complex samples | Reusable FIR outputs per residual scan | Entire covariance rows reusable |
| --- | ---: | ---: | ---: | ---: |
| Physical prospective | 32 / 19 / 14 | 3,415 | 200 | 0 |
| Weak-carrier challenges, both pilot edges | 36 / 36 / 22 | 3,262 | 200 | 0 |
| Public northern simulation | 80 / 25 / 2 | 3,287 | 200–228 | 0 |
| Public southern simulation | 80 / 12 / 0 | 2,609 | 200 | 0 |

The largest native unchanged count was 7,679 out of 200,000. Most additional unchanged samples were too isolated to produce a new complete FIR stencil. The native code and component tests check both physical lanes independently, the two pilot edges, clipping at partial frames and epochs close to both sides of the frame wrap. The public prefixes are simulated geographic development checks.

## Cost ceiling

The audit's native equality scan reads two full stereo buffers and emits unchanged intervals. It took 9.64 ms across the 92 residuals, about 105 µs per scan. A separate warm 1.6 MB copy took 8.96 ms total. These costs exclude Python interval accounting. Known geometric gaps need no additional equality scan. The frozen first-pass FIR results are still in their original array before the residual FIR runs.

Applying the observed mean unchanged fractions to the measured per-scan input-conversion and FIR clocks gives about **3.43 µs per residual scan** of free reuse before bookkeeping or copies. That is **0.04%** of the 0.821 s complete native receiver cost on these slices. A deliberately generous stage budget applies the largest observed clean fractions to **all** input-conversion and FIR time in the packed receiver profile, including the first scan. That would remove **0.27%** of native CPU, before any lookup or copying. Changed covariance rows and global modes leave no measurable FFT budget in this method. [Packed receiver stage profile](receiver-stencil-results.json)

## Reproduce

The helper calls the frozen receiver's actual timing acquisition and cancellation on each lane. It uses the same pinned assets, a separate fully evaluated factor call, and a small native equality and memcpy probe for timing. The inputs are 16 existing prospective stereo visits, 18 physical weak challenges and 40 scheduled visits of each public simulation. The native receiver was `950c2b9412020317654fd7c79d30063e9258b70152ed9c91b4129d379ac75a13`.

```bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_python=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src timeout 80s "$@"
}

algo08_lock cc -O3 -std=c11 -fPIC -shared -Wall -Wextra -Werror \
  tools/pipeline_eval/variants/experimental/receiver_cancel_support.c \
  -o "$algo08_work/receiver-cancel-support.so"
algo08_lock "$algo08_python" -m tools.pipeline_eval.variants.experimental.receiver_cancel_support \
  "$algo08_work/receiver-stencil.so" "$algo08_work/receiver-cancel-support.so" \
  /srv/bulk/leo-dev/ds26-two-carrier-20261120/prospective-iq.zip \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_20_single_scan_glrt/satellite-reference.zip \
  /tmp/leo-regional-qZJKBw4W/public/panel.json --assets /opt/leo-algo08/current/assets
algo08_lock "$algo08_python" -m pytest -q tests/pipeline_eval/test_experimental_receiver_cancel_support.py
```

All three component tests passed. The work consists of a measurement helper, with both scientific receiver passes supplied by the frozen binary.
