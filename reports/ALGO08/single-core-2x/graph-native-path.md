# Exact native Graph path selection

This saved-detection experiment measures `prepare_tracks` between fast-scan detection and the orbital solver. It uses the sealed deployed and packed Q15 outputs for dense DS30-0008 and the already published northern inside simulation. The paired comparison reruns Graph on identical bytes for each input. The detector-to-detector comparison separately follows the numerical differences already present in those inputs. [Inputs and measurements](measurements/graph-native-path.json) · [Earlier detector comparison](measurements/full-phase-0008-selections.json)

The previous track preparation profiler measured the Python path search. The native implementation packs each lane's incoming and outgoing edges once in their original order and evaluates the same second-order recurrence in C with ordered binary64 arithmetic and disabled contraction. Strict comparisons preserve the preference for the two-point base and the first predecessor or terminating edge at a tie. NumPy computes the cumulative alias lifts. The stock caller handles availability, rejected-path edge removal, alternate paths, and polynomial finalization. A missing library, unsupported architecture, invalid packing or ineligible numeric range uses the reference recurrence. [Earlier profiler](../../../tools/pipeline_eval/qualification/track_preparation_profile.py) · [Adapter](../../../tools/pipeline_eval/variants/experimental/graph_path.py) · [Kernel](../../../tools/pipeline_eval/variants/experimental/graph_path.c) · [Tests](../../../tests/pipeline_eval/test_graph_native_path.py)

The shadow replay required matching path, lifted CFO array, edge IDs and scalar score bits on each call. It verified all 442 calls across the three inputs. Independently, the complete prepared output digests match between the reference and native implementations for each input, including ordered track memberships, polynomial coefficients and residual diagnostics.

## CPU on Gauss

| Saved detections | Reference Graph CPU | Native Graph CPU | Reference path CPU | Native path and packing CPU | Native calls |
|---|---:|---:|---:|---:|---:|
| DS30-0008 deployed | 2.363 s | 1.690 s | 516.9 ms | 21.2 ms | 201 |
| DS30-0008 packed Q15 | 2.450 s | 1.766 s | 525.8 ms | 21.8 ms | 201 |
| North public inside | 0.133 s | 0.115 s | 10.5 ms | 2.1 ms | 40 |

A packed-input repeat ran native first and reference second in the same process. It measured 2.199 → 1.713 CPU seconds for the complete stage and 490.1 → 22.1 ms for path search with packing. The directly timed gain attributable to this change is about half a CPU second on the dense input and 8 ms on the public input. The reference-forward pairs also had timing variation elsewhere in the stage. Dense polynomial proposals and common finalization took 1.17–1.18 and 0.46 seconds respectively in those reference runs. [Raw stage clocks](measurements/graph-native-path.json)

## Source of the dense membership change

The two dense detections agreed on winning rank or no detection for all 13,530 opportunities and on the Graph timestamps of all 7,016 winners. Three winning CFO values moved by at most 17.63 µHz. The 16 lane topologies, 201 selected edge chains and proposed polynomial memberships all matched between inputs. Both results contain 236 tracks with the same 111 active curved keys. Final membership changed only on RX2/CH6 track T002, which lost 11 observations and gained nine.

The affected lane has one changed input value, a CFO shift of +1.2175 µHz at 117.9295396 s. At the first changed ownership row, at 95.2529447 s, proposal 3 beat proposal 2 in the deployed input by 0.000000000116415 Hz. Both circular residuals were about 31.49 Hz, comfortably within the 450 Hz gate. The packed input gave the two proposals exactly equal residuals of 31.494012567491154 Hz, and the strict comparison retained proposal 2. The first ensuing support change presented to `_best_piece` is call 133, indexed from zero across the lane. Both fits choose degree four, on 69 and 67 observations respectively. The symmetric difference of those supports matches the 20 final ownership changes by observation ID. [Polynomial and ownership readouts](measurements/graph-native-path.json) · [Finalization code](../../../src/leo/analysis/tracklet_fitting.py)

## Reproduction

Specify the deployed DS30-0008, Q15 DS30-0008, and public north inside factors in that order. The asset and input digests, sealed paths and raw CPU readings are in the receipt. This command uses the installed release virtual environment, the research checkout and the single-core Gauss lock.

```bash
cd /tmp/leo-algo08v2-2x
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
bench=/tmp/leo-algo08v2-2x-bench
sealed=/tmp/ds30-v2-stage-full-phase-50d300/DS30-0008
baseline=("$sealed"/baseline/fast-scan-automatic-work/*/detections.json)
packed=("$sealed"/candidate/fast-scan-automatic-work/*/detections.json)
north=("$bench"/combined-q15-repair-north-inside/fast-scan-automatic-work/*/detections.json)
export PYTHONPATH="$PWD:$release/src:$release"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
locked=(flock "$bench/gauss.lock" nice -n 15 ionice -c 2 -n 7 taskset -c 2)
trial=("$release/venv/bin/python" -B reports/ALGO08/single-core-2x/graph_saved_trial.py
       "$release/assets/tracks.json" "${baseline[@]}" "${packed[@]}" "${north[@]}")
"${locked[@]}" "${trial[@]}" --library "$bench/graph-path-v1.so" --build --verify
"${locked[@]}" "${trial[@]}" --timing --audit-polynomial
"${locked[@]}" "${trial[@]}" --timing --library "$bench/graph-path-v1.so"
```

Each replay begins with saved detection documents and ends at the complete prepared Graph output. The shadow check and polynomial readout run outside the reported timings.

## Frozen research launcher

Add `--graph-path LIBRARY SHA256` to the chosen research freeze. The freezer checks the library digest and native ABI version before it creates the bundle. The bundle pins the copied library, C source and Python adapter. The launcher checks those pins and the installed reference Graph source, then loads the checked bytes from its private asset directory. Ineligible lanes still use the Python recurrence. The original polynomial proposal and finalization code handles ownership, including its original carrier aliases. The opt-in result reports native path counts and CPU times under `graph_path`.

With the environment above, build the current ABI and add it to a freeze using the reviewed detector and digest.

```bash
graph_library="$bench/graph-path-v1.so"
"${locked[@]}" "$release/venv/bin/python" -B -c \
  'from pathlib import Path; from sys import argv; from tools.pipeline_eval.variants.experimental.graph_path import build; build(Path(argv[1]))' \
  "$graph_library"
read -r graph_sha256 _ < <(sha256sum "$graph_library")
"$release/venv/bin/python" -B -m tools.pipeline_eval.qualification.freeze_publication \
  "$output" "$detector" "$detector_sha256" --solver stock --ingress stock \
  --graph-path "$graph_library" "$graph_sha256"
```

The earlier timing receipt used the same recurrence before the ABI version export was added. Rebuild older Graph libraries for the frozen launcher.
