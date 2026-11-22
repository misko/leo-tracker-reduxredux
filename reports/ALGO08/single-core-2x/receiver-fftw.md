# Hardware-specific FFTW wisdom for the packed receiver

Precomputed FFTW plans cut the three transform kernels by **22–25%** on Gauss and full native two-scan receiver CPU by **1.1–2.0%**. All ordered factor values and continuation outputs matched on the physical and public simulation prefixes. FFT execution accounted for **7–9%** of native receiver CPU in the separate instrumented replay. [Measurement receipt](receiver-fftw-results.json)

## Plan creation and loading

The packed `950c2b94` receiver creates three one-thread, in-place single-precision FFTW plans with `FFTW_ESTIMATE`. Its stride-4 timing search uses length 4,800 in both directions and its carrier stage uses length 4,096 forward. The older measured-wisdom study covered a different 21-row inverse batch. No earlier study in this build series measured the packed receiver's three plans. [Original planner](../../../tools/pipeline_eval/variants/experimental/receiver_fftw.inc) · [Older inverse batch planner](../../../tools/pipeline_eval/variants/fft_length_plan.py)

One offline `FFTW_MEASURE` pass used the stock 8,192-element aligned scratch allocation, fixed FFT shapes and a 1.5-second limit per shape. The planner receives no recording or geographic input. On the Intel Core Ultra 9 285K pinned to CPU 2 with FFTW 3.3.10, this took 0.925 CPU seconds and 1.035 elapsed seconds, including all three searches. The exported wisdom string was 2,087 bytes. [Builder and planner](../../../tools/pipeline_eval/variants/experimental/receiver_fftw_wisdom.py)

The opt-in loader checks the architecture, CPU fingerprint and FFTW version. Receiver setup isolates the imported wisdom under the planner lock, requests all three plans with `FFTW_WISDOM_ONLY` and restores the previous FFTW wisdom. With missing, malformed, incompatible or incomplete wisdom, it uses the three stock estimate plans. Plan search belongs to the offline builder. [Runtime overlay](../../../tools/pipeline_eval/variants/experimental/receiver_fftw_wisdom.inc) · [Fallback tests](../../../tests/pipeline_eval/test_experimental_receiver_fftw_wisdom.py)

## Native receiver comparison

The physical trial uses the first 80 scheduled visits of the sealed DS30-0016 recording. Each public simulation contributes its first 40 visits. Both use the normal admission policy and independent state for each replay of the released continuation. Four repetitions reverse which receiver goes first at each lane. The frozen `950c2b94` library is the control. Timing covers complete native factor calls, including any residual scout, cancellation and original-I/Q verification. Receiver context opening is measured separately. [Runner](receiver_fftw_trial.py) · [Frozen receiver](receiver-stencil.md)

| Saved prefix | Admitted lanes | Rank 0 / rank 1 factors | Rank 0 / rank 1 continuation selections | Native CPU per repeat, control → wisdom | Paired CPU saving |
|---|---:|---:|---:|---:|---:|
| DS30-0016 | 146 | 73 / 25 | 22 / 1 | 545–561 → 536–552 ms | 1.1–1.8% |
| Public north and south | 160 | 35 / 2 | 0 / 0 | 417–425 → 410–416 ms | 1.7–2.0% |

Both arms produced the same integer epochs, fractional offsets, CFOs, exact correlations, rolled-control correlations and factor ranks. The ordered factor and continuation digests matched. The continuation comparison includes preference, selected factor and vote counts.

## Transform and setup costs

Two additional repeats timed the transforms with the same instrumentation in both arms. The timers surround the FFT execution calls and exclude the inverse scaling loop. Setup transforms are excluded from the table. Scheduled transform counts matched in each case. [Measurement receipt](receiver-fftw-results.json)

| Saved prefix | FFT calls per arm | Forward timing FFT CPU | Backward timing FFT CPU | Forward carrier FFT CPU | Total FFT execution CPU |
|---|---:|---:|---:|---:|---:|
| DS30-0016 | 17,520 | 21.48 → 18.10 ms | 19.72 → 15.11 ms | 39.73 → 29.90 ms | 80.93 → 63.11 ms |
| Public north and south | 15,760 | 18.79 → 15.55 ms | 17.86 → 13.06 ms | 35.69 → 25.48 ms | 72.34 → 54.09 ms |

The isolated planner step rose from 0.046–0.061 ms per context with estimate to 0.455–0.506 ms with wisdom. Import itself took 0.107–0.110 ms per context. The remaining setup time includes saving and restoring the process's existing FFTW state, creating the three imported plans and releasing the planner lock. Complete context opening rose by 0.39–0.64 ms in the instrumented comparison. The measured work leaves FFT planning as a small receiver optimization.

## Reproduce

Use the same release assets and the known packed binary. Run the builder, one offline planner pass and the replay under the shared Gauss lock on one pinned low-priority core. The replay needs a capture account that can read the sealed physical slices. The instrumented control needs a second physical copy of the overlay so it has independent configuration.

```sh
work=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
module=tools.pipeline_eval.variants.experimental.receiver_fftw_wisdom
physical_binding=/srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0016.json
public_panel=/tmp/leo-regional-qZJKBw4W/public/panel.json
lock() {
  flock "$work/gauss.lock" nice -n 15 ionice -c 2 -n 7 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    PYTHONPATH="$PWD:$release/src:$release" "$@"
}
lock timeout 35s "$release/venv/bin/python" -B -m "$module" build "$work/receiver-fftw-wisdom.so"
lock timeout 15s "$release/venv/bin/python" -B -m "$module" measure "$work/new-fftw-wisdom.json"
cp "$work/receiver-fftw-wisdom.so" "$work/receiver-fftw-estimate.so"
lock timeout 45s "$release/venv/bin/python" -B \
  reports/ALGO08/single-core-2x/receiver_fftw_trial.py \
  "$work/receiver-stencil.so" "$work/receiver-fftw-wisdom.so" \
  "$work/receiver-fftw-estimate.so" "$work/new-fftw-wisdom.json" \
  "$physical_binding" "$public_panel" "$release/assets"
```
