# Guarded frame-relative verification with site-free PGO

The full-scan Q15 and packed frame-relative verifier saved **7.41%** median paired native CPU on the DS30-0016 chronological prefix versus the full floating-FIR PGO receiver. Keeping the floating FIR and changing only the guarded verifier saved **6.20%**. Across 436 lanes, both composed builds preserved all **255 ordered factors**, including **69 residuals**, and all **53 causal continuation selections** by rank, integer and fractional timing, and signed CFO. Score differences appeared on 183 lanes, with a maximum margin difference of **1.08 × 10⁻¹³**. [Frozen build manifest](measurements/phase-packed-pgo-manifest.json) · [Physical comparisons](measurements/phase-packed-pgo-physical.json) · [Off-site comparisons](measurements/phase-packed-pgo-offsite.json)

## Prespecified build comparison

The designated combination uses both unconditional scouts, Q15 FIR, the existing packed coarse and fractional interpolation kernels, and the existing guarded frame-relative verifier. The earlier frame-relative route interpolates each fractional sample separately. The new route applies the existing group-of-four interpolation and four ordered symbol sums to both precombined templates. The original frame-relative scalar kernel remains available without AVX2/FMA. The spectrum, margin and rank-order guard still calls the original packed absolute-phase verifier on ambiguous evidence. The floating-FIR diagnostic keeps the same scouts as the control. [Earlier verifier and fallback](receiver-fractional-phase.md) · [Q15 FIR](receiver-integer-fir.md) · [Packed mixed kernel](../../../tools/pipeline_eval/variants/experimental/receiver_phase_packed_mixed.inc)

The freeze preceded scoring. Both new libraries used the existing eight generated dual-antenna windows across both pilot edges and four signed CFOs. GCC 15.2 collected branch counts in all ten translation units with value profiling disabled and required matching coverage data when applying feedback. The training source is pinned to SHA-256 `250e5ac9025c04abcf34b20b5b8c4a8d6efe4525e7252739bf20c94d161f1557`. It saw no archive waveforms while training. [Compiler procedure](receiver-compiler.md)

| Full-scan build | Detector SHA-256 |
| --- | --- |
| Floating FIR reference | `cc06336a86d06b356d0b7394c55a10e6e5d81471fbe2215a4c88be405f2762b8` |
| Q15 FIR only | `64432addf6997f1ebd45daa8e73fd8337d0ab6abbeade254f611055542b71ea3` |
| Floating FIR plus packed frame-relative verifier | `dd2d83a8cc865b156115922e057823300e269c2fcb65f525f81e6fa620ed1a20` |
| Q15 FIR plus packed frame-relative verifier | `107b4f3deb588d68c0b286be1cf22ba3e183a849f9b96f63fd440a583acd962e` |

## Complete native-call timings

All percentages are medians of paired savings against the floating-FIR reference. Five repeats rotate and reverse call order over lanes in the physical and public simulated archives. The Austin single-antenna excerpt uses nine repeats on its four physical and four phase-randomized cases. DS30-0016 begins with empty continuation state and reads at most 128 scheduled windows. It admits 116 stereo windows under the released rule.

| Slice | Lanes | Reference factors / residuals | Q15 only | Float + verifier | Q15 + verifier |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0016 chronological prefix | 232 | 152 / 41 | 2.45% | 6.20% | 7.41% |
| Weak-carrier physical archive | 36 | 58 / 22 | 1.44% | 8.70% | 11.54% |
| Austin measured field | 4 | 8 / 4 | 0.67% | 11.38% | 13.99% |
| Austin phase nulls | 4 | 0 / 0 | 1.98% | 0.73% | 3.04% |
| Public northern simulation prefix | 80 | 25 / 2 | 1.73% | 3.97% | 6.23% |
| Public southern simulation prefix | 80 | 12 / 0 | 1.85% | 2.22% | 3.88% |

The chronological median total native CPU was 0.736515 seconds for the control, 0.721194 for Q15, 0.695794 for the floating verifier variant, and 0.682665 for both changes. Gains varied with verified signal activity. The Austin nulls never invoked the fractional verifier. The acquisition, solver, and publication costs fall outside these clocks. Closing a 2.734-second budget gap at the chronological native percentages would require about 36.9 seconds of reference native work with Q15, or 44.1 seconds with the floating FIR. This trial measures no DS30-0155 native time.

## Numerical evidence

All tested factor counts, their order, and continuation states agreed. The two frame-relative builds had identical maximum absolute changes of **8.50 × 10⁻¹⁴** in exact-pilot score, **4.39 × 10⁻¹⁴** in rolled score and **1.08 × 10⁻¹³** in margin. Each fell back six times in 258 attempted verifications per repeat across the slices. There were no ranking retries or changes to the released factor gate or the strong-margin class. The changed continuous margins remain inputs to the solver's radio uncertainty fit. Earlier saved perturbation tests preserved both position arms on cases that chose constant variance. The earlier complete conditional Q15 replay added three primary measurements outside this chronological prefix, which establishes a separate scout-level risk. [Margin consumers](receiver-fractional-score-consumers.md) · [Full conditional Q15 receipt](measurements/guard-q15-ds30-0016.json)

Twelve component tests passed. The new mixed-reference test checks the scalar and packed symbol correlation bytes together with start-index and coefficient-row changes and signed zeros. The original guarded verifier and packed fractional tests cover measured pilots and ambiguous spectra. [New component tests](../../../tests/pipeline_eval/test_experimental_receiver_phase_packed.py)

## Reproduce

Use a new build directory for the freeze. The saved manifest contains resolved detector paths and hashes. The two archived PGO reference binaries must reproduce their pinned digests.

~~~sh
work=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
study="$tree/reports/2026_11_19_receiver_screening"
reports=reports/ALGO08/single-core-2x
trial="$reports/receiver_phase_pgo_trial.py"
python="$tree/.venv/bin/python"
assets=/opt/leo-algo08/current/assets
manifest="$work/site-free-phase-packed-pgo-rebuild-manifest.json"

algo08_lock() {
  flock -x "$work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="src:.:$reports" timeout 80s "$@"
}
algo08_lock "$python" "$trial" freeze "$work/site-free-phase-packed-pgo-rebuild" "$assets" \
  "$work/site-free-compiler-floating-full/use.so" "$work/site-free-compiler-v2/use.so" > "$manifest"
algo08_lock sudo -n -u leo -- env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH="src:.:$reports" PYTHONDONTWRITEBYTECODE=1 /opt/leo-algo08/current/venv/bin/python \
  "$trial" physical "$manifest" "$assets" /srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0016.json \
  "$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip"
algo08_lock "$python" "$trial" offsite "$manifest" "$assets" /tmp/leo-regional-qZJKBw4W/public/panel.json \
  /home/mouse9911/.cache/austin-waveform-20261119/exemplar250-257.zip \
  "$study/physical/raw-source-audit.json" "$study/arrival-and-timing/austin-waveform/native-outputs.jsonl.gz"
algo08_lock "$python" -m pytest -q tests/pipeline_eval/test_experimental_receiver_phase_packed.py \
  tests/pipeline_eval/test_experimental_receiver_phase_free.py \
  tests/pipeline_eval/test_experimental_receiver_fractional_batch.py \
  tests/pipeline_eval/test_experimental_receiver_integer_fir.py
~~~
