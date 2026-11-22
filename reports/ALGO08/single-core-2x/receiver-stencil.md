# Sharing verifier loads across neighboring integer epochs

Packing four of the five neighboring timing epochs saved **2.7–3.1% native CPU** on the prospective physical slice. It preserved every exported factor and continuation decision across **356 saved lanes**, including the weak-carrier challenges and the two public simulation prefixes. The two-carrier search, cancellation and final fractional verifier keep their full 20 ms support. [Matched receipts](receiver-stencil-results.json)

## What changed

The frozen `107909cc` receiver already prepares one integer oscillator table per CFO and uses hardware FMA. Its five stencil entries still each scan the same pilot and oscillator tables. The packed kernel loads four consecutive I/Q samples for the four adjacent epoch hypotheses. It broadcasts the same complex oscillator and pilot values to them. For each tap it computes the same two complex fused products. Each epoch retains the original four tap accumulation chains, which are reduced as `(0 + 1) + (2 + 3)`. The existing spectrum, tie handling and fractional interpolation receive the five inputs in their original order.

The fifth entry uses the existing correlation kernel. The complete original stencil also handles wraparound, distinct numbers of complete frames at the two ends of the stencil, CPUs without AVX2 and FMA, and the separate diagnostic path that needs the five rolled-control scores. The production factor path still uses the full exact-versus-rolled fractional gate. The pilot tables and coefficients depend on the existing waveform and RF input metadata. Both physical receiver lanes are evaluated independently.

## Matched comparison

Three repeats alternate the first call over visits, receiver lanes and repeat index. Counts refer to unique tested lanes and their exported factors. The simulated rows combine existing 40-visit prefixes from the public northern and southern recordings. These simulations are geographic development checks.

| Saved slice | Lanes | All factors | Residual factors | Native CPU saved |
| --- | ---: | ---: | ---: | ---: |
| Physical prospective | 160 | 141 | 55 | 2.7–3.1% |
| Weak-carrier challenges | 36 | 58 | 22 | 2.2–2.8% |
| Public north and south | 160 | 37 | 2 | 1.2–1.6% |

All tuples and ordered output digests were identical. The saved slices had no continuation selections, and the comparison found no disagreement in their continuation states. The component tests compare the packed and original symbol correlations byte for byte, and compare the complete verifier outputs on signed CFOs, a planted fractional pilot, a silent lane, period wrap and frame-support boundaries. An alternate layout with four separate real and imaginary vector elements also matched all 160 prospective lanes. It saved 2.7–2.9% on that slice, so the interleaved layout was chosen before the publication pair.

The instrumented prospective replay measured 282 complete verifier calls over two repeats. The verifier stage fell from **0.2689 to 0.2382 CPU seconds** (11.4%), and full native lane calls fell from **1.3164 to 1.2868 CPU seconds** (2.2%). [Stage profile](receiver-stencil-results.json)

## Reproduce

The default experimental receiver is the frozen reference. The packed trial adds `--pack-stencil`, with native ABI and compiler recipe otherwise identical. The tested packed binary SHA-256 is `950c2b9412020317654fd7c79d30063e9258b70152ed9c91b4129d379ac75a13`.

```bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_python=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
algo08_native=tools.pipeline_eval.variants.experimental
algo08_reference="$algo08_work/receiver-final-candidate.so"
algo08_packed="$algo08_work/receiver-stencil.so"
algo08_assets=/opt/leo-algo08/current/assets

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src timeout 80s "$@"
}

algo08_lock "$algo08_python" -m "$algo08_native.receiver_build" "$algo08_packed" --pack-stencil
algo08_lock "$algo08_python" -m "$algo08_native.receiver_benchmark" \
  /srv/bulk/leo-dev/ds26-two-carrier-20261120/prospective-iq.zip \
  "$algo08_reference" "$algo08_packed" --visits 80 --repeats 3 --assets "$algo08_assets"
algo08_lock "$algo08_python" -m "$algo08_native.receiver_benchmark" \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_20_single_scan_glrt/satellite-reference.zip \
  "$algo08_reference" "$algo08_packed" --visits 18 --repeats 3 --assets "$algo08_assets"
algo08_lock "$algo08_python" -m "$algo08_native.receiver_benchmark" \
  /tmp/leo-regional-qZJKBw4W/public/panel.json "$algo08_reference" "$algo08_packed" \
  --simulated-panel --visits 40 --repeats 3 --assets "$algo08_assets"
algo08_lock "$algo08_python" -m pytest -q tests/pipeline_eval/test_experimental_receiver_stencil.py
```

The tested build reproduced its SHA-256 exactly and both component tests passed. For the separate instrumented comparison, add `--profile` to both build commands and use two repeats on the prospective slice.
