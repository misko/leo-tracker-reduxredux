# Exact vector arithmetic around the two-mode scout FFTs

Packed scout arithmetic saved **5.81%** native CPU on the DS26 weak-carrier slice against combined receiver `14b52e7e…`. The measured Austin inputs saved **4.05–5.74%**. All **74 factor records and 52 continuation results** matched exactly, including 30 signed residual factors. [Paired and instrumented clocks](measurements/receiver-spectral-vectors.json.gz)

The combined frame-plane receiver still builds two independent complex principal modes for the raw window and again from the quantized signed residual. The cancellation support audit found at most 228 unchanged FIR stencils in 50,000 outputs and no entirely unchanged covariance rows. Sharing the first mode or spectrum would lose information needed by the second scout. Within one scout, the familiar two-real-input FFT trick relies on conjugate symmetry. Both mode streams here are complex. Mapping `x, y` to one complex stream `x + i y` is many-to-one, since `x + d, y + i d` produces the same stream for arbitrary complex `d`. The two carrier FFTs per epoch remain separate. [Signed residual support](receiver-cancel-support.md) · [Frame planes](receiver-frame-planes.md) · [Earlier FFTW planning experiment](receiver-fftw.md)

The prototype preserves the FFT plans and covers both modes and every original timing and signed carrier bin. It packs the lag products, spectral multiplication, despreading, and independent power additions into AVX2 lanes. The prefix energy and carrier energy still accumulate in their original sample order in Float64. The lag score applies the existing Float32 inverse scale when loading each of the 3,333 retained epochs, instead of scaling all 4,800 inverse results in a separate walk. It then computes the same capped denominator, division and per-lag addition for each retained epoch. The original strict maxima, candidate spacing, ranking and full-rate signed gates use these scores. Unsupported CPUs take the original computation. [Vector kernels](../../../tools/pipeline_eval/variants/experimental/receiver_spectral_vectors.inc) · [Overlay](../../../tools/pipeline_eval/variants/experimental/receiver_spectral_vectors.py)

The earlier blocked selector sought savings in repeated maxima. This test keeps the selector and addresses the lag/correlation and carrier arithmetic that prepares its inputs. Timing and carrier search together accounted for 22.4% of the earlier packed receiver's weak-carrier native profile. The new experiment isolates these two stages on matched, instrumented builds in addition to timing complete native calls on the uninstrumented receiver. Every newly compiled timing object trains on the same site-free generated waveforms used for the earlier receiver. [Earlier stage clocks](measurements/receiver-packed-cancellation.json) · [Blocked maxima trial](receiver-epoch-blocks.md)

| Saved configuration | Calls per repeat | Combined reference median CPU | Vector arithmetic median CPU | Median paired saving |
|---|---:|---:|---:|---:|
| DS26 weak-carrier stereo | 36 | 128.14 ms | 120.37 ms | 5.81% |
| Austin measured, zero center | 4 | 14.79 ms | 13.83 ms | 5.74% |
| Austin measured, shifted center | 4 | 18.76 ms | 17.85 ms | 4.05% |
| Austin phase nulls, zero center | 4 | 6.13 ms | 5.67 ms | 6.31% |
| Austin phase nulls, shifted center | 4 | 7.38 ms | 6.88 ms | 8.03% |

Twelve repeats alternate arm order. The weak-carrier slice preserves 36 primary and 22 residual factors. The Austin measured inputs preserve 16 factor records across both mixer-center configurations. Both phase-null configurations remain empty. All continuation preferences, votes and selections agree. The sparse sampled history supplies no continued selections. The median native saving is **208 µs per weak-carrier lane**. At that rate, the earlier 9,288-lane physical recording would save about 1.94 CPU s, conditional on the same scout mix and rate. This is a receiver-only projection. [Paired weak and Austin receipt](measurements/receiver-spectral-vectors.json.gz) · [Physical lane count](measurements/screened-tiled-ds30-stage.json)

The matched instrumented arms execute 432 scouts each. Timing search drops from **112.28 to 72.91 ms** (35.1%) and carrier search from **72.75 to 61.60 ms** (15.3%). The two stages save roughly **117 µs per scout**. Eliminating both original measured stages entirely would cap this stage budget at about **0.86 ms per two-scout lane**. Six component tests compare full lag products, zero padding, ordered energy prefixes, filtered complex values, timing scores, and carrier powers. They exercise both widths, unequal tails, signed zeros, and the positive lower denominator floor. [Matched stage profiles](measurements/receiver-spectral-vectors.json.gz) · [Intermediate array checks](../../../tests/pipeline_eval/test_experimental_receiver_spectral_vectors.py)

The measured uninstrumented receiver is `/tmp/leo-algo08v2-2x-bench/spectral-vectors-combined-v1/packed/use.so`, SHA-256 `b63cf5b0b70e142a246fefd40b7ceb8ba2a24ecf0b4e8d0a05c6901cdef5dd94`. Its rebuilt timing object SHA-256 is `5ffc8eb34785b7d20535549da23ba521cf954f86b6cfabce96c0c71ac664292d`. The original wrapped refinement dispatcher, tiled FIR, signed cancellation, and verifier are inherited byte for byte. [Native build and object digest](measurements/receiver-spectral-vectors.json.gz)

## Additional parity checks and terminal-guard freeze

Both receivers passed 24 generated configurations through the normal CI16 native entry point. The exact zero timing ties and sparse ±1 ADC-count tests each returned no factors across eight lane configurations. Eight equal-strength, opposite-CFO overlap configurations each returned both a primary and a residual. The 16 factors and all continuation outputs were identical. The configurations cover both pilot edges and zero and signed nonzero mixer centers. [Generated parity receipt](measurements/receiver-spectral-vectors-generated.json.gz) · [Generator and archived check](receiver_spectral_vectors_check.py)

The three authenticated wrapped CFO regression lanes from DS30-0008 reproduced all five archived factors, byte for byte against the full restoration. Primary CFOs were 423233.6713368766, −85797.21886355223, and −96538.83871655293 Hz. [Regression receipt](measurements/receiver-spectral-vectors-regression.json) · [Original wrapped trace](receiver-cfo-lineage.md)

The research bundle `/tmp/leo-algo08v2-2x-bench/integration-spectral-vectors-terminal-veto` has specification `sha256:23fadeb79c76c343760dc3fb107f7dfb170b0ba4eec22a4dc3df244c2187cf24`. Its parent is terminal-guard `977e7dd6…`. The freezer verifies the parent, detector binary, timing source and object, native output and regression receipts, and both new source pins. The specification and receiver bytes change, with two new source files. The solver, terminal guard, manifests, launcher, and other inherited file bytes match the parent. Ten component tests passed, including tamper checks for inherited sources, new sources, and the receiver. The frozen bundle is for a later paired publication. [Freeze receipt](measurements/spectral-vectors-terminal-veto-freeze.json) · [Freezer](freeze_spectral_vectors_receiver.py) · [Freeze tests](../../../tests/pipeline_eval/test_freeze_spectral_vectors_receiver.py)

## Reproduce

Use the already verified combined receiver and its archived object and source pins. The builder relinks the combined reference byte for byte, rebuilds only the timing object, and verifies the public symbols. It adds the same clock object to both instrumented arms. The saved controls are the 18-window DS26 weak archive and the authenticated Austin excerpt on both pilot edges, with zero and shifted mixer-center configurations. No position solver or publication runs in this benchmark. [Runner](receiver_spectral_vectors_trial.py) · [Component tests](../../../tests/pipeline_eval/test_experimental_receiver_spectral_vectors.py)

~~~bash
p=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
t=reports/ALGO08/single-core-2x
r=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
hist="$tree/reports/2026_11_19_receiver_screening"
lock() {
  flock -x "$p/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src:.:$t" timeout 80s "$@"
}
lock "$tree/.venv/bin/python" -m pytest -q \
  tests/pipeline_eval/test_experimental_receiver_spectral_vectors.py
lock "$tree/.venv/bin/python" -m reports.ALGO08.single-core-2x.receiver_spectral_vectors_trial \
  "$p/spectral-vectors-rebuild" "$p" "$r/assets" \
  "$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" \
  /home/mouse9911/.cache/austin-waveform-20261119/exemplar250-257.zip \
  "$hist/physical/raw-source-audit.json" "$hist/arrival-and-timing/austin-waveform/native-outputs.jsonl.gz"
~~~

The recorded freeze used these checks with the measured build and receipt names. The regression reads only the three previously authorized saved lanes.

~~~bash
candidate="$p/spectral-vectors-combined-v1/packed/use.so"
saved=/tmp/ds30-v2-stage-covariance-375895/DS30-0008
lock "$tree/.venv/bin/python" -m reports.ALGO08.single-core-2x.receiver_spectral_vectors_check \
  generated "$p/d97b-planes-and-fir/receiver.so" "$candidate" "$r/assets" \
  > "$p/spectral-vectors-generated.json"
lock sudo -n -u leo -- env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src:.:$t" "$r/venv/bin/python" -BPs \
  -m reports.ALGO08.single-core-2x.receiver_spectral_vectors_check regression \
  "$candidate" "$p" "$r/assets" "$saved/pair.json" \
  "$saved/candidate/fast-scan-automatic-work/algo08-v2-3dce9426edd1831eade2003d69a00297/detections.json" \
  /srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0008.json /srv/bulk \
  > "$p/spectral-vectors-regression.json"
lock "$tree/.venv/bin/python" -m reports.ALGO08.single-core-2x.freeze_spectral_vectors_receiver \
  "$p" "$p/integration-frame-plane-terminal-veto" "$candidate" \
  "$p/integration-spectral-vectors-terminal-veto" "$p/spectral-vectors-terminal-veto-freeze.json"
~~~
