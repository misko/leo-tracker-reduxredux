# Exact packed interpolation for fractional pilot verification

Evaluating four neighboring Lanczos outputs together reduced verifier CPU by **19.2%** in the prospective profile. Complete native receiver CPU fell **2.8–3.3%** on the chronological physical prefix. Across five saved slices, all **388 factors**, including **120 second-scan factors**, and all **53 continuation selections** matched the packed coarse-bank reference. The quieter public southern prefix showed no consistent CPU savings. [Matched receipts](receiver-fractional-batch-results.json)

## Exact fractional arithmetic

The five integer scores already choose a single fractional position. The verifier measures the exact and rolled pilot at that position using absolute sample coordinates. The earlier frame-relative oscillator experiment changed those scores by up to \(1.97\times10^{-13}\). Recomputing each selected score exactly left 0.6–0.9% net native CPU savings on the physical prefix. The continuous margin remains an input to the estimator's radio uncertainty fit. [Frame-relative verifier](receiver-fractional-phase.md) · [Score repair and consumers](receiver-fractional-score-consumers.md)

The packed kernel checks that four adjacent interpolated outputs use consecutive sample starts and the same rounded coefficient row. The two AVX2 registers each hold a pair of complex outputs. Each Lanczos coefficient is broadcast once and applied to all four overlapping 16-tap windows using contiguous loads. Each output still has the four original interleaved sums, with the same final pairwise reduction. At a coefficient-row or sample-start transition, each interpolation follows the original scalar routine.

The packed outputs then use the existing absolute oscillator values and the same fused complex multiply for the exact and rolled references. The symbol correlation retains the original four ordered sums. The score spectrum, normalization, residual-frequency calculation, timing, gates and both signed cancellation passes keep their original inputs and arithmetic. Systems without AVX2 and FMA use the original correlation function. The kernel relies on the waveform and its rounded interpolation geometry.

## Matched native receiver calls

| Saved slice | Lanes | Factors / second-scan factors | Native CPU saved |
| --- | ---: | ---: | ---: |
| Physical prospective archive | 160 | 141 / 55 | 3.3–3.9% |
| Physical weak-carrier challenges | 36 | 58 / 22 | 4.2–4.4% |
| Public northern simulation prefix | 80 | 25 / 2 | 1.0–1.5% |
| Public southern simulation prefix | 80 | 12 / 0 | −0.34% to +0.23% |
| Chronological DS30-0016 prefix | 232 | 152 / 41 | 2.8–3.3% |

Three repeats alternate call order over visits and antennas. The chronological trial processes the first 128 scheduled visits, of which 116 pass the original capture-quality policy. Continuation keeps 52 first-scan and one second-scan factor. The public prefixes are geographic development simulations. The timed boundary is the complete native detector call after receiver setup.

Two instrumented prospective repeats measured **0.2413 → 0.1950 CPU seconds** across 282 verifier calls. Native CPU for both repeats was **1.2587 → 1.2118 seconds**. The verifier profile includes the integer stencil, correlation and full score calculation. It accounted for 19.2% of reference native CPU, so eliminating the entire verifier would give an upper limit of about **1.24×** on this receiver call. The measurements cover the receiver component.

A second exact variant used adjacent-register shuffles to reconstruct overlapping I/Q loads. It produced the same factor digest in four prospective repeats. It increased complete native CPU by **1.5–2.0%** relative to the direct packed loads. The frozen candidate uses the direct loads.

## Reproduce

The reference is `474279618ca68abc95f8f350e9fdd8e98dc76ca3b789b14a5489859972556269`. The added `--fractional-batch` option builds `c5fca3e240f5415a061ce17057ef215070767d23cae4932b9a1d566217eae420`. Both binaries rebuilt byte for byte.

~~~bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_tree=/home/mouse9911/gits/leo-tracker-reduxredux
algo08_python="$algo08_tree/.venv/bin/python"
algo08_native=tools.pipeline_eval.variants.experimental
algo08_assets=/opt/leo-algo08/current/assets
algo08_reference="$algo08_work/receiver-refine-bank-ordered.so"
algo08_fractional="$algo08_work/receiver-fractional-batch.so"
algo08_prospective=/srv/bulk/leo-dev/ds26-two-carrier-20261120/prospective-iq.zip
algo08_weak="$algo08_tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip"
algo08_panel=/tmp/leo-regional-qZJKBw4W/public/panel.json

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src:. timeout 80s "$@"
}
algo08_lock "$algo08_python" -m "$algo08_native.receiver_build" \
  "$algo08_reference" --pack-stencil --batch-refine
algo08_lock "$algo08_python" -m "$algo08_native.receiver_build" \
  "$algo08_fractional" --pack-stencil --batch-refine --fractional-batch
algo08_lock "$algo08_python" -m "$algo08_native.receiver_benchmark" \
  "$algo08_prospective" "$algo08_reference" "$algo08_fractional" \
  --visits 80 --repeats 3 --assets "$algo08_assets"
algo08_lock "$algo08_python" -m "$algo08_native.receiver_benchmark" \
  "$algo08_weak" "$algo08_reference" "$algo08_fractional" \
  --visits 18 --repeats 3 --assets "$algo08_assets"
algo08_lock "$algo08_python" -m "$algo08_native.receiver_benchmark" \
  "$algo08_panel" "$algo08_reference" "$algo08_fractional" \
  --visits 40 --repeats 3 --assets "$algo08_assets" --simulated-panel
algo08_lock "$algo08_python" -m pytest -q \
  tests/pipeline_eval/test_experimental_receiver_fractional_batch.py \
  tests/pipeline_eval/test_experimental_receiver_stencil.py \
  tests/pipeline_eval/test_experimental_receiver_refine_bank.py
~~~

The regional timings group `read_simulated_prefix(panel, 40)` by recording and call `receiver_benchmark.benchmark` independently. The chronological trial passes `list(receiver_brackets.read_physical(binding, Path("/srv/bulk"), 128))` for the DS30-0016 binding to the same benchmark in the release environment. The stage profile adds `--profile` to both builds and uses two repeats on the 80 prospective visits. The 12 component tests passed. Direct comparisons cover discontinuous sample starts, coefficient-row transitions, signed CFOs on both pilot edges and a silent lane.
