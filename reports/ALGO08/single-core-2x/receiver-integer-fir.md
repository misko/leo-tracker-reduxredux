# Packed Q15 FIR for the two-scan timing scout

The opt-in integer FIR cut quarter-rate decimation CPU by **37.8%** and complete native receiver CPU by **2.7–3.8%** across five saved slices. The comparisons returned the same **388 ordered factors**, including **120 signed-residual factors**, and the same **53 continuation selections**. The existing two-entry residual build also composed with the FIR and matched each exported raw factor on a chronological physical prefix. This is a component result for one CPU and these inputs. [Archive comparisons and stage profile](receiver-integer-fir-results.json) · [Chronological and dual-entry comparison](receiver-integer-fir-chronological.json)

## Kernel and error

The 81-tap FIR for the original and cancelled I/Q streams keeps its 10 MS/s input, quarter-rate output, sampling origin and aperture. Signed Q15 FIR weights are shared across the I and Q dot products of one antenna. The two planar int16 input arrays use 800 kB of scratch stack and are reused sequentially across scans and lanes. The Intel AVX-VNNI instructions accumulate pairs of signed 16-bit products into 32 bits. The integer path requires symmetric coefficients and a bound of `32768 × sum(abs(weights)) ≤ INT32_MAX` for every reduction. Both production pilot assets have a quantized L1 sum of 57,645. The scout template uses the original floating filter. The first and last ten decimated samples use the floating filter's edge arithmetic. Unsupported ISA, filter geometry or coefficients use the floating FIR.

At zero mixing center, the input conversion retains every CI16 component exactly. A nonzero center uses half scaling before rounding the floating-point mixed components, with one input count maximum error when expressed at the original scale. The coefficient error on the pinned FIR has an L1 sum of 0.000381. This bounds the coefficient contribution to the output error at 0.000381 times the largest input component. Mixed input also incurs an output rounding term bounded by the quantized FIR's L1 norm times one input count. These are input-domain bounds, with additional floating-point rounding at conversion and comparison. They do not certify the nonlinear scout's candidate ordering or detect an omitted proposal. Full-rate signed refinement, cancellation and the exact-versus-rolled verification all use their existing input and arithmetic. An exact completeness fallback would need to demonstrate that omitted proposals cannot change the result or rerun the reference scout.

The earlier AVX-VNNI experiment implemented an int8 template screen for a different detector. The earlier sample-rate experiment considered removing half the FIR output bandwidth. This trial applies integer dot products to the current receiver's 81-tap quarter-rate FIR on both scans. [Earlier template screen](../../../tools/pipeline_eval/variants/screened_detector_grid.c) · [Earlier rate experiment](receiver-rate.md) · [Integer FIR kernel](../../../tools/pipeline_eval/variants/experimental/receiver_integer_fir.inc)

## Matched single-core measurements

| Slice | Lane calls per arm | Factors / residual factors | Native CPU saved |
| --- | ---: | ---: | ---: |
| Prospective physical archive | 160 | 141 / 55 | 2.75–2.85% |
| Physical weak-carrier archive | 36 | 58 / 22 | 3.37–3.75% |
| Public northern simulation prefix | 80 | 25 / 2 | 2.74–3.29% |
| Public southern simulation prefix | 80 | 12 / 0 | 2.91–3.33% |
| Chronological DS30-0016 prefix | 232 | 152 / 41 | 2.81–3.10% |

Each slice used three repeats and alternated the arm order across visit, lane and repeat. The chronological trial read the first 128 scheduled visits, of which 116 passed released admission for both lanes. Continuation kept 52 first-scan factors and one residual factor with equal published values. The benchmark clocks complete native factor calls, excluding I/Q reads, decode, setup and Python continuation. The simulations are geographic development inputs. All saved comparisons used a zero mixer center. Component tests separately cover finite mixed inputs, negative int16 endpoints, exact output edges and floating fallback.

Two instrumented prospective repeats recorded **0.10854 → 0.06754 CPU seconds** in FIR across 492 scouts, including the integer path's conversion and boundary work. Complete native time was 1.09830 → 1.06439 seconds in those repeats. The reference FIR represented 9.88% of total native CPU. Removing its whole cost would cap this direction at about **1.11× native speedup**. The measured saving is modest even before the rest of acquisition and publication.

## Dual-entry composition

The dual-entry candidate exports `cancellation_factors` and `cancellation_primary_factors`, both with the established factor ABI. On the same 232 chronological physical lanes, the full entry returned 111 primary and 41 residual factors. Its raw-only counterpart returned 111 primary factors. Every value and returned order matched the pinned dual-entry reference in all three repeats. Native CPU savings were 1.86–2.30% for full calls and 2.95–3.18% for primary-only calls. Both routes use the same FIR fallback. This composition test times the two entries separately.

| Binary | SHA-256 |
| --- | --- |
| Full exact reference | `c5fca3e240f5415a061ce17057ef215070767d23cae4932b9a1d566217eae420` |
| Full integer FIR | `8982c1b6cadbe80659f9f7cf8456746472d0f693c2dd363bd4e9a282adaf83e0` |
| Dual-entry exact reference | `1b4c43dc1f2edc64ead9c4b9c0f4d724f79f623e04a13f40812a1d4bb40345a5` |
| Dual-entry integer FIR | `c34c55748bd9b5feac6f1736e27acb78b4a1caa97f0d13a50b604cffd61d2d70` |

## Guarded research publication

The `conditional-residual` research launcher accepts the legacy or Q15 dual-entry detector only when its bytes match the approved SHA-256 selected in the specification. The freezer verifies those bytes and pins the original causal schedule, adapter and native binary in the source manifest. The guarded Q15-only specification, with canonical digest `sha256:e174cfdd19b0c23b2ac3ffbc4f4506c6b2ab310bf43fc25a7854d5c0f8e4f080`, uses the same shared-table solver, decoded SHA ingress, renderer and guard as the prior guarded configuration. Its source manifest differs at the detector, pin list and launcher digest check. [Guarded reference configuration](regional-bound-guard.md) · [One-run comparator](receiver_q15_publication_trial.py)

The complete saved DS30-0016 recording took **11.415 CPU seconds and 11.772 elapsed seconds** in one candidate-only run. It used the same sealed recording, fixed offer and capture-time orbit archive as the saved conditional control. The control's selected local endpoints were more than 4.6 km inside the 25 km search square, so its selected solution would bypass the regional guard. Both runs admitted 713 of 808 windows and requested the same 872 full and 554 primary-only native calls.

- Q15 retained all 439 control selections and added three rank-zero selections at visits 179, 219 and 275, all on channel 4 on receiver 1. The ordered 1,426 probe identities and acquisition metadata matched.
- Both runs fixed with identical zero-calibration and fitted-calibration endpoints, satellite owners, numerical path and grid. Frequency RMS stayed at 109.375 Hz and 109.479 Hz for the two respective calibration arms.
- All eight PNGs verified and decoded. Five matched encoded bytes and decoded RGBA hashes, including the position and track-RMS figures. The three channel 1–4 diagnostics changed decoded pixels.

The publication result shows equal position evidence on this input and a difference in selected radio evidence. The short-slice factor parity section above covers different inputs. Launcher and freezer coverage includes the legacy pin, the Q15 pin, modified bytes, and substitution of one approved build for the other. **41 publication and receiver tests passed.** [Single-run science, timings and PNG hashes](measurements/guard-q15-ds30-0016.json) · [Saved conditional control](measurements/DS30-0016-conditional-reverse.json)

~~~sh
algo08_work=/tmp/leo-algo08v2-2x-bench
flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 80s \
  sudo -n -u leo -- env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 /opt/leo-algo08/current/venv/bin/python \
  -m reports.ALGO08.single-core-2x.receiver_q15_publication_trial \
  /tmp/leo-conditional-residual-0016-candidate-first/pair.json \
  "$algo08_work/integration-conditional-residual-regional-veto-q15/spec.json" \
  /tmp/leo-guard-conditional-q15-ds30-0016-reproduction
~~~

## Reproduce

~~~bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_tree=/home/mouse9911/gits/leo-tracker-reduxredux
algo08_python="$algo08_tree/.venv/bin/python"
algo08_native=tools.pipeline_eval.variants.experimental
algo08_assets=/opt/leo-algo08/current/assets
algo08_script=reports/ALGO08/single-core-2x/receiver_integer_fir_benchmark.py

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src:. timeout 80s "$@"
}
for algo08_arm in fractional-batch integer-fir; do
  algo08_flags=()
  if [[ "$algo08_arm" == integer-fir ]]; then algo08_flags+=(--integer-fir); fi
  algo08_lock "$algo08_python" -m "$algo08_native.receiver_build" \
    "$algo08_work/receiver-$algo08_arm.so" --pack-stencil --batch-refine --fractional-batch "${algo08_flags[@]}"
  algo08_lock "$algo08_python" -m "$algo08_native.receiver_build" \
    "$algo08_work/receiver-$algo08_arm-profile.so" --pack-stencil --batch-refine --fractional-batch \
    --profile "${algo08_flags[@]}"
  algo08_lock "$algo08_python" -m "$algo08_native.receiver_residual_build" \
    "$algo08_work/receiver-dual-$algo08_arm.so" --fractional-batch "${algo08_flags[@]}"
done

algo08_lock "$algo08_python" "$algo08_script" archives \
  "$algo08_work/receiver-fractional-batch.so" "$algo08_work/receiver-integer-fir.so" \
  "$algo08_work/receiver-fractional-batch-profile.so" "$algo08_work/receiver-integer-fir-profile.so" \
  "$algo08_assets" /srv/bulk/leo-dev/ds26-two-carrier-20261120/prospective-iq.zip \
  "$algo08_tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" \
  /tmp/leo-regional-qZJKBw4W/public/panel.json

algo08_lock sudo -n -u leo -- env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 /opt/leo-algo08/current/venv/bin/python \
  "$algo08_script" chronological \
  "$algo08_work/receiver-fractional-batch.so" "$algo08_work/receiver-integer-fir.so" \
  "$algo08_work/receiver-dual-fractional-batch.so" "$algo08_work/receiver-dual-integer-fir.so" \
  "$algo08_assets" /srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0016.json

algo08_lock "$algo08_python" -m pytest -q \
  tests/pipeline_eval/test_experimental_receiver_integer_fir.py \
  tests/pipeline_eval/test_residual_native_build.py
~~~
