# Contiguous conditioning sums in the ALGO08v3 likelihood

The densest captured native call took **107.681 ms with the released code and 106.309 ms with contiguous conditioning sums**. The other three activated calls were 0.2% to 1.9% slower. All eight captured calls returned identical posterior fields, convergence and fallback counts. The measurements stop at the likelihood kernel. [Trial runner](solver_column_norms_trial.py)

The native solver computes a Gram column norm before Schur elimination and bounds the inverse column norm before accepting the resulting factor. Both checks originally revisit each private row at strided addresses for every shared column. The trial computes each dense column sum first, then traverses private rows in their original group order with consecutive shared-column lanes. Each lane sees the original operands and addition order. The variational updates, condition thresholds, input grouping, finite differences and factorization order are identical. The experiment builds separate ordinary and posterior-export binaries from the pinned native source. [Implementation](../../../tools/pipeline_eval/variants/algo08_column_norms.h) · [Build and binding](../../../tools/pipeline_eval/variants/algo08_column_norms.py)

The witnesses came from the archived dense DS30-0008 roof solve and southern containing simulation. The trial used the released native binary and one warmed owner per library and input. The medians use 12 alternating process CPU measurements per arm with one numerical thread, CPU 2, `nice -n15`, `ionice -c2 -n7`, and exclusive access through the Gauss lock. The four fallback witnesses include width-five native layout rejects and southern conditioning rejects. [Capture procedure](solver-wide-private-blocks.md)

| Input and likelihood | Route | Precision updates | Released CPU (ms) | Contiguous CPU (ms) |
|---|---|---:|---:|---:|
| DS30-0008 history | Native | 39 | 12.939 | 12.963 |
| DS30-0008 position | Native | 256 | 107.681 | 106.309 |
| DS30-0008 position | Width fallback | 65 | 117.830 | 117.366 |
| Southern history | Native | 43 | 5.731 | 5.843 |
| Southern position | Native | 38 | 6.500 | 6.590 |
| Southern history | Conditioning fallback | 46 | 15.390 | 15.342 |
| Southern position | Conditioning fallback | 32 | 11.478 | 11.474 |
| Southern position | Width fallback | 30 | 10.935 | 10.958 |

The synthetic suite verified unshared and shared designs, one and two private columns, a zero column, the existing layout and conditioning fallbacks, and the exported posterior factor and permutation. Twelve tests passed across the new component, posterior handoff and release launcher. The experiment covered no complete-solve or raw publication comparisons. [Component tests](../../../tests/pipeline_eval/test_algo08_column_norms.py)

The earlier dense profile spent 14.099 CPU seconds in native likelihood calls. Applying the fastest observed reduction, 1.27%, across that entire historic budget would save about 0.18 seconds. Transferring that CPU saving directly to the 113.02-second frozen DS30-0008 raw run gives an optimistic **1.002×** speedup. The 83 dense Python fallback calls in that profile are outside this kernel. [Dense profile](restored-scout-0008-solver-profile.md) · [ALGO08v3 stage clocks](../v3/first-55/stage-clocks.csv)

## Reproduction

From the experiment worktree, build into a fresh local directory and reuse the archived likelihood inputs. The comparison writes a fresh receipt and raises on any numerical or route difference.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
bench=/tmp/leo-algo08v2-2x-bench
build=$(mktemp -d)/column-norms
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1
export PYTHONPATH="$PWD/src:$PWD"
"$release/venv/bin/python" -BPs -c \
  'from pathlib import Path; from sys import argv; from tools.pipeline_eval.variants.algo08_column_norms import build; build(Path(argv[1]))' \
  "$build"
flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  "$release/venv/bin/python" -BPs \
  reports/ALGO08/single-core-2x/solver_column_norms_trial.py \
  "$release/assets/native/native_bound.so" "$build/column-norms-bound.so" "$build/kernel.json" \
  "$bench/dense-likelihood-capture-0008" "$bench/dense-likelihood-capture-south"
```
