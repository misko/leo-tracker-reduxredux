# Exact signed pilot cancellation with packed subtraction and reused block norms

The packed cancellation reduced median paired complete native CPU by **6.81%** on 18 archived stereo weak-carrier visits. All **58 ordered factors**, including 22 second-scan factors, kept the same epochs, signed carriers, and verified scores. The saved physical call counts leave about **1.16–2.58 s** of potential CPU saving at the observed per-cancellation rate. This supplies a candidate for a combined publication improvement, with no measured three-second standalone saving. [Matched timings and binary pins](measurements/receiver-packed-cancellation.json)

The c803 physical publication took 46.126 s from launch to detections. The d44c paired-covariance receiver used in that publication still produced the signed residual in a scalar loop, emitting every corrected Float32 sample after rounding to CI16. The compiler inlines `lrint` as a scalar conversion with separate lower and upper clipping checks. In an earlier weak-carrier profile, 108 cancellations took 67.05 ms, approximately 620 μs per cancellation and 14.4% of complete native CPU in that selected slice. The physical publication recorded 9,288 admitted lane calls and 4,157 continued factors. The saved selected rows give a lower count of calls that must have reached cancellation. The full publication did not measure how many additional calls reached that stage. [Physical stage receipt](measurements/screened-tiled-ds30-stage.json) · [Earlier paired-covariance profile](measurements/receiver-epoch-blocks.json)

The packed variant keeps the original oscillator recurrence, computes every rotated pilot value through the same Float32 cast and writes it in its one-of-three tick phase. Adjacent lane samples are three synthesis ticks apart, so a block's pilot values become contiguous. It then computes the complex subtraction and clipping in binary64 and rounds two I/Q pairs at a time. The rounding instruction uses the current nearest mode. Unsupported CPUs and non-nearest rounding use the original resident cancellation. The original separate stereo-scratch path also remains in use at nonzero mixer centers. [Packed kernel](../../../tools/pipeline_eval/variants/experimental/receiver_cancel_packed.inc)

The same complete pilot block and tick phase use the same ordered template samples every time they recur within a lane call. Their squared norm is independent of the received samples. A 15-entry scratch table reuses this exact binary64 sum for full blocks. Partial edge blocks compute their own norm. The complex gain dot products retain their original accumulation order and use their own measured I/Q for every block, carrier and antenna. The receiver still runs both full timing and carrier scouts, applies signed cancellation and verifies the proposed factors on the original I/Q. The new code does not require phase or CFO history across visits. The earlier residual-sharing experiment considered reuse across raw and residual FIR or covariance input. This variant computes the entire signed residual with the original arithmetic. [Previous residual reuse bound](receiver-cancel-support.md)

The comparison relinks the available PGO object files and requires the exact frozen SHA-256 in each reference arm. It recompiles only the cancellation translation unit and trains that object on the existing generated zero and nonzero center signals. It reads the same 18 archived stereo weak-carrier visits used in the blocked timing study and alternates arm order over visits, lanes and repeats. The clocks include complete native calls, with the stage attribution measured separately on instrumented builds. Seven component tests cover full residual equality near frame wrap, the CFO limits, rounding and clipping, the odd tail, and non-nearest fallback. [Trial driver](receiver_cancel_packed_trial.py) · [Component tests](../../../tests/pipeline_eval/test_experimental_receiver_cancel_packed.py)

| Measured quantity | Frozen reference | Packed cancellation |
|---|---:|---:|
| Median complete receiver CPU across five repeats of 36 lanes | 145.957 ms | 136.152 ms |
| Complete CPU in separate instrumented repeats, 180 lanes | 730.940 ms | 677.868 ms |
| Cancellation CPU in those repeats, 180 signed corrections | 109.262 ms | 59.210 ms |

The instrumented comparison isolates **278 μs per cancellation** (45.8%). Every lane in these selected weak-carrier visits reached a signed cancellation. Both antennas and both pilot edges contributed. Ordered factors and every continuation decision matched, and the short separated sample produced no continued selection. At the same 278 μs per call, applying the change to 4,157 calls gives 1.16 s, and assuming all 9,288 admitted lanes cancel at zero mix gives 2.58 s. Saving 3 s on that recording would require at least 323 μs per call even if every lane reached the optimized correction. These are fixed-rate projections from the archived subset. Actual reach rates, mixer bounds, and per-call times can change the result. The trial ends at native receiver factors and continuation. [Per-stage clocks](measurements/receiver-packed-cancellation.json) · [Frozen physical comparison](screened-tiled-publication.md)

## Independent Austin excerpt

The same sealed binary retained both ordered factors on all four physical edge and window combinations at zero mixer center. Changing only the detector bounds to exercise the fallback at −50 kHz on the lower edge and +50 kHz on the upper edge again produced identical factors against the frozen reference, including signed CFO, integer and fractional epoch, and exact and rolled scores. All eight phase-null configurations returned zero factors. All 16 continuation results, including preference and votes, matched. The 20 ms spacing falls short of the released 0.4 s vote span. The strongest factor agreed with the authors' relative timing in each physical configuration, with a maximum discrepancy of **0.645 sample** at 10 MS/s. Both windows use the same measured antenna. [Per-window evidence](measurements/receiver-packed-cancellation-austin.json) · [Independent source and timing reference](austin-receiver.md)

The uninstrumented candidate SHA-256 is `88b4f3ba6479b287cd581c604afa796992a2e6c7cbd34761d176f24500123f03`. Its full detector ABI is the same as d44c. Both scouts run as scheduled by the original native code. The generated cancellation source SHA-256 is `34e186b48005ec68ad9a16024a691b12c9ad71d06e40985104ce086cf077d3f0`, and the included kernel SHA-256 is `a311944fb7ac88f19f99020a502a345337cff53f484171d88e48f50aa0c8b41f`. GCC 15.2.0 rebuilt that translation unit using the generic `-ffp-contract=off` recipe with one balanced site-free profile. The reviewed c803 build and qualification settings were left as published. [Parent receiver rebuild recipe](receiver-mode-pair.md#frozen-builds-and-tests)

~~~sh
p=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
t=reports/ALGO08/single-core-2x
r=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
lock() {
  flock -x "$p/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src:.:$t" timeout 80s "$@"
}
lock "$tree/.venv/bin/python" -m pytest -q tests/pipeline_eval/test_experimental_receiver_cancel_packed.py
lock "$tree/.venv/bin/python" "$t/receiver_cancel_packed_trial.py" trial \
  "$p/c803-packed-cancel-rebuild" "$p/site-free-mode-pair-pgo" \
  "$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" "$r/assets" \
  > "$p/c803-packed-cancel-rebuild.json"
hist="$tree/reports/2026_11_19_receiver_screening"
lock "$tree/.venv/bin/python" "$t/receiver_cancel_packed_trial.py" offsite \
  "$p/c803-packed-cancel-rebuild" "$p/c803-packed-cancel-rebuild.json" \
  /home/mouse9911/.cache/austin-waveform-20261119/exemplar250-257.zip \
  "$hist/physical/raw-source-audit.json" \
  "$hist/arrival-and-timing/austin-waveform/native-outputs.jsonl.gz" "$r/assets"
~~~
