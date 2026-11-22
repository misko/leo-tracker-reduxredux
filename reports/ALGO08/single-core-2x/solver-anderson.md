# Safeguarded Anderson precision updates

The depth-three Anderson experiment failed the predeclared kernel admission gates. The hardest captured DS30-0008 call exhausted all 256 accelerated updates, then replayed stock. Its posterior was byte-identical and its CPU cost increased from **107.17 to 215.79 ms**. Two other supported calls exceeded the allowed change in individual posterior terms despite near-identical total ELBO. The experiment stopped at captured kernels. [Frozen protocol](solver-anderson-protocol.md) · [Measured receipts](measurements/solver-anderson-witnesses.json)

The research library cold-starts every likelihood and changes only the sequence of Gamma-rate updates after four ordinary mappings. It tests each candidate’s actual update residual against the computed ordinary successor. Stock geometry, conditioning, rate floors, update cap, and the `1e-5` convergence check remain in the call. An exhausted or numerically failed candidate replays the original cold call. This uses a depth-three constrained combination of mapped log rates and a separately evaluated ordinary comparator. The earlier two-step SQUAREM experiment used a different safeguard and changed northern assignments. The implementation and differential gates were committed in `887d6f5e2` before testing. [Prototype](../../../tools/pipeline_eval/variants/algo08_anderson.h) · [Earlier SQUAREM](solver-robust-updates.md)

| Already captured supported call | Returned updates, stock → experiment | Median CPU, stock → experiment | Verified proposals, accepted / tried | Failed admission gates |
|---|---:|---:|---:|---|
| Physical history, 3,574 × 243 | 39 → 39 | 12.85 → 13.27 ms | 1 / 1 | Quadratic and Gamma terms |
| Physical position, 4,522 × 255 | 256 → 256 | 107.17 → 215.79 ms | 3 / 7 | Dense CPU |
| Southern history, 4,122 × 103 | 43 → 44 | 6.00 → 6.18 ms | 0 / 1 | None |
| Southern position, 5,323 × 99 | 38 → 36 | 6.63 → 6.61 ms | 1 / 1 | Quadratic, Gamma and normalized residual |

The capped physical call’s final change after the cold replay was `3.825e-4`, over 38 times the stock stopping tolerance. It required the entire 256-step accelerated attempt and the entire cold replay. The other physical call changed the quadratic by `9.03e-5` and the Gamma cost by `9.19e-5`, against a `1e-5` limit per term. Their combined ELBO difference was `9.68e-10`. The southern accepted proposal changed the quadratic by `6.36e-5`, Gamma cost by `5.77e-5`, and one normalized residual by `1.17e-5`. Its total ELBO changed by `1.09e-8`. The four width or conditioning fallback witnesses returned byte-identical posteriors. [All returned quantities and timing gates](measurements/solver-anderson-witnesses.json)

The dense call is one witness from the 99-call workload that performed 18,750 updates. The stock result’s finite budget matters because a more converged solution can differ from the published solver’s output. For an exact route, first measure whether any Schur blocks survive Gamma reweighting byte-for-byte across those updates. Factor reuse needs an exact unchanged-input check and a meaningful share of the 39.9 ms per captured call already spent in LAPACK. This trial measured neither reuse nor a publication speedup. [Dense workload and native cost](solver-wide-private-blocks.md)

## Reproduction

Use the existing captured likelihood inputs under the Gauss lock. The runner compiles the experiment, uses five alternating measured calls after warmup, and reports the frozen gates. Give it new binary and result filenames.

```sh
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  PYTHONPATH="$PWD:$PWD/src:$release" "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.single-core-2x.solver_anderson_trial \
  "$release/assets/native/native_bound.so" "$new_library" "$new_receipt" \
  "$bench/dense-likelihood-capture-0008" "$bench/dense-likelihood-capture-south"
```
