# Sharing integer coarse refinement within each scout

The exact refinement bank saved **2.8–4.0% of complete native receiver CPU** across five small saved slices. It preserved the ordered tuples of all **388 exported factors**, including **120 signed residual factors**, and all **53 causal continuation selections** across **588 lanes**. Both pilot scouts, both actual antennas and the full window remain in use. [Matched receipts](receiver-coarse-bank-results.json)

Each scout already nominates four signed CFO and timing seeds. For each seed, coarse refinement uses nine nearby integer offsets, 14 complete frames and eight pilot blocks of 352 taps. The frozen kernel already prepares the pilot and oscillator product once per seed. Its first four blocks keep four interleaved Float32 sums per offset. Its last four blocks use serial Float32 sums and an overlapping four-offset SIMD stencil. The earlier five-offset verifier optimization runs at a later stage of the detector. [Frozen refinement](receiver.md) · [Integer verifier stencil](receiver-stencil.md)

The bank packs eight distinct neighboring offsets into AVX2 registers and computes the ninth with the corresponding serial or four-chain reduction. Two seeds at the same epoch share received I/Q loads and sample-power sums. Identical CFO bit patterns within a scout share the original oscillator recurrence. The bank returns the refinements in input order and reuses the pinned scalar score, CFO correction, timing interpolation and tie handling. Period wrap and unsupported CPUs use the original correlation. The subsequent gates, cancellation, residual scout and fractional verification keep the original paths. The optimization uses only the waveform, pilot references and released search bounds.

## Saved native receiver comparisons

| Slice | Lanes | Factors / residual factors | Native CPU saved |
| --- | ---: | ---: | ---: |
| Physical prospective archive | 160 | 141 / 55 | 3.6–4.0% |
| Weak-carrier challenges | 36 | 58 / 22 | 2.9–3.6% |
| Public northern simulation prefix | 80 | 25 / 2 | 3.2–3.8% |
| Public southern simulation prefix | 80 | 12 / 0 | 3.0–3.6% |
| Chronological physical DS30-0016 prefix | 232 | 152 / 41 | 2.8–3.3% |

The three repeats alternate first call over visits, receivers and repeat index. The chronological trial reads at most 128 scheduled visits and applies the original quality policy before evaluating the 116 valid windows. It selects 52 first-scan and one residual observation through normal continuation. The public prefixes are geographic development simulations. These timings include the complete native receiver call with plans and assets initialized. The measurements cover the receiver component.

## Remaining ceiling

An argument trace on the first 16 prospective snapshots, all 18 weak snapshots and the two 40-visit simulation prefixes counted 320 scouts and 1,280 actual seed calls. It found **112 repeated epochs** in the same scout and no other overlap among the nine native offsets. The **141** repeated CFOs were 114 in the northern simulation, 25 in the southern simulation, two in the weak slice and zero in the prospective slice. Different CFOs at the same epoch still require separate coherent products. The bank pairs up to two requests for that shared load. It keeps the original path on the one observed wrap seed.

Prepacking real, imaginary and squared-power arrays per frame produced the same factor digest in a separate A/B. Across three prospective repeats it changed complete native CPU by −0.13% to +0.28% relative to the in-register version, including the cost of building the packed arrays. The in-register version is the frozen candidate.

Two instrumented repeats measured coarse refinement at **0.2050 → 0.1532 CPU seconds**, a 25.3% reduction, with complete native CPU at **1.3452 → 1.2968 seconds**. The reference timed 1,968 individual seeds and the candidate timed their 492 complete banks. Removing even that entire stage would cap speedup at about **1.18×** over the packed reference.

The quarter-rate scout power and full-rate refined score use different statistics. A power-only Cauchy–Schwarz enclosure of the normalized refined score reaches one, so it cannot discard an uncorrelated seed against a measured score below one. Both immediate neighbors of the winning integer sample also supply the reported fractional timing. FFT convolution or partial-score rejection would need a rounding enclosure and an ordered fallback to preserve those values and the strict tie rule.

## Reproduce

The disabled flag rebuilt the packed reference to SHA-256 `950c2b9412020317654fd7c79d30063e9258b70152ed9c91b4129d379ac75a13`. The frozen exact candidate rebuilt to `474279618ca68abc95f8f350e9fdd8e98dc76ca3b789b14a5489859972556269`.

~~~bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_tree=/home/mouse9911/gits/leo-tracker-reduxredux
algo08_python="$algo08_tree/.venv/bin/python"
algo08_native=tools.pipeline_eval.variants.experimental
algo08_assets=/opt/leo-algo08/current/assets
algo08_reference="$algo08_work/receiver-stencil.so"
algo08_bank="$algo08_work/receiver-refine-bank-ordered.so"
algo08_prospective=/srv/bulk/leo-dev/ds26-two-carrier-20261120/prospective-iq.zip
algo08_weak="$algo08_tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip"
algo08_panel=/tmp/leo-regional-qZJKBw4W/public/panel.json

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src:. timeout 80s "$@"
}
algo08_lock "$algo08_python" -m "$algo08_native.receiver_build" "$algo08_reference" --pack-stencil
algo08_lock "$algo08_python" -m "$algo08_native.receiver_build" "$algo08_bank" --pack-stencil --batch-refine
algo08_lock "$algo08_python" -m "$algo08_native.receiver_benchmark" \
  "$algo08_prospective" "$algo08_reference" "$algo08_bank" --visits 80 --repeats 3 --assets "$algo08_assets"
algo08_lock "$algo08_python" -m "$algo08_native.receiver_benchmark" \
  "$algo08_weak" "$algo08_reference" "$algo08_bank" --visits 18 --repeats 3 --assets "$algo08_assets"
algo08_lock "$algo08_python" -m "$algo08_native.receiver_benchmark" \
  "$algo08_panel" "$algo08_reference" "$algo08_bank" --visits 40 --repeats 3 \
  --assets "$algo08_assets" --simulated-panel
algo08_lock "$algo08_python" -m pytest -q \
  tests/pipeline_eval/test_experimental_receiver_refine_bank.py \
  tests/pipeline_eval/test_experimental_receiver_stencil.py
~~~

The reported regional timings group `read_simulated_prefix(panel, 40)` by `case` and call `receiver_benchmark.benchmark` for each recording. The chronological trial passes `list(receiver_brackets.read_physical(binding, Path("/srv/bulk"), 128))` for `/srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0016.json` to that benchmark in the release environment. The profile adds `--profile` to both builds and measures two repeats on the 80 prospective visits. The nine component tests passed, including bytewise per-seed comparisons over repeated epochs, repeated frequencies, signed-zero CFO, offset wrap, exact ties and oversized banks.
