# Reuse input vectors across four exact quarter-rate FIR outputs

The tiled AVX2 FIR saved **20.9–21.1%** of isolated FIR CPU and **2.22%** of complete native CPU on the saved DS26 weak-carrier lanes. The complete-call median paired saving was **87 µs per lane**. All **66 factors**, including 26 from independent signed residual scouts, retained their ranks, epochs, signed CFOs, and scores. This matches the wrapped-only `d97b…` successor on the archived inputs. The FIR's measured cost puts a one-millisecond-per-lane saving outside this stage's budget. [Complete timings, factor comparisons and link commands](measurements/receiver-fir-tile.json)

The original quarter-rate kernel already folds symmetric weights and has four independent Float32 accumulation chains per I/Q pair. Neighboring output centers are four input samples apart. As the loop moves to the next four-tap group, three of four left vectors and three of four right vectors are the exact vectors needed by a neighboring output. The tile reuses those loaded vectors and their left-side reversals. A four-output interior block reads 26 vectors where the original four independent outputs read 80. Each output still visits its ten coefficient groups in order, and adds the four final values to the central term in its original order. The first and last ten outputs use the original bounded-edge arithmetic. Unsupported ISA, other strides or orders, and overlapping buffers use the archived entry point. [Kernel](../../../tools/pipeline_eval/variants/experimental/receiver_fir_tile.c)

FFT FIR would change the rounding order of the existing Float32 folded reductions. A local exact check near the coarse winner does not certify the omitted lower-ranked proposals, which still contribute to the nonlinear covariance and timing search. The earlier Q15 FIR already measured a large stage speedup with a full-support factor difference on a longer recording. Reusing identical samples between the two scouts was bounded by the signed cancellation support audit. This experiment holds the entire FIR calculation and both scouts fixed in meaning. It changes data movement within each individual pass. [Q15 experiment](receiver-integer-fir.md) · [Signed support audit](receiver-cancel-support.md) · [Earlier FFTW study](receiver-fftw.md)

| Measured boundary | Native calls per repeat | Wrapped → tiled median CPU | Median paired saving |
|---|---:|---:|---:|
| Isolated FIR, two pinned pilot assets and two input representations | 1 | 182–183 → 144 µs | 20.9–21.1% |
| DS26 physical weak-carrier stereo | 36 | 141.02 → 137.18 ms | 2.22% |
| Austin measured pilot edges | 4 | 16.34 → 15.95 ms | 2.49% |
| Austin phase-null controls | 4 | 6.97 → 6.77 ms | 1.97% |

The synthetic stage check compares every output byte for both pinned assets and CI16-derived or fractional Float32 input. The complete weak-carrier result compares 18 saved stereo windows, including both signed carrier directions, and all nine paired repeats saved CPU. The Austin result compares two disjoint 20 ms windows of one measured antenna at both pilot edges. The Austin timings span few calls and include zero-center calls only. Both paths returned no phase-null factors. The sparse weak-carrier archive produced no continued selections. Three component tests cover the entire output, unaligned input, signed zeros, clipped stencils, supported shape, aliased output, and fallback geometry. [Prior signed field readout on the same weak windows](receiver-cfo-native.md) · [Austin archive provenance](austin-receiver.md) · [Tests](../../../tests/pipeline_eval/test_experimental_receiver_fir_tile.py)

The earlier packed-cancellation profile attributes 68.27 ms to 360 FIR passes, about **190 µs per pass**. At two passes per lane, eliminating the whole measured stage would save roughly **0.38 ms per lane**. Applying the observed ~38 µs per pass to all 9,288 admitted lanes in the previous DS30-0374 physical receipt would save at most about **0.72 CPU s** at that rate, assuming every lane reaches two scouts. The trial measures no complete acquisition or publication. [Earlier FIR clocks](measurements/receiver-packed-cancellation.json) · [Earlier physical stage receipt](measurements/screened-tiled-ds30-stage.json)

The candidate SHA-256 is `cb57aa1e83463ccb7fe491115f961bb21f565736838eee110d7b398a974f1898`. The build first relinks the wrapped comparison library byte for byte. It renames the original FIR entry, links the experimental entry, then verifies the exported ABI and archived refinement instructions. Wrapped CFO restoration and signed cancellation remain on the original objects. [Wrapped lineage](receiver-cfo-wrap.md) · [Build and test driver](receiver_fir_tile_trial.py)

~~~sh
p=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
t=reports/ALGO08/single-core-2x
r=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
hist="$tree/reports/2026_11_19_receiver_screening"
flock -x "$p/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src:.:$t" timeout 65s \
  "$tree/.venv/bin/python" -m reports.ALGO08.single-core-2x.receiver_fir_tile_trial \
  "$p/d97b-fir-tile-rebuild" "$p" "$r/assets" \
  "$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" \
  /home/mouse9911/.cache/austin-waveform-20261119/exemplar250-257.zip \
  "$hist/physical/raw-source-audit.json" "$hist/arrival-and-timing/austin-waveform/native-outputs.jsonl.gz"
~~~
