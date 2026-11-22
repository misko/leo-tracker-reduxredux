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

The dense call is one witness from the 99-call workload that performed 18,750 updates. The stock result’s finite budget matters because a more converged solution can differ from the published solver’s output. Factor reuse needs exact unchanged inputs and a meaningful share of the 39.9 ms per captured call already spent in LAPACK. [Dense workload and native cost](solver-wide-private-blocks.md)

## Exact Schur reuse audit

The stock trajectory produced **zero repeated whole Schur matrices, factor inputs or Cholesky factors** on the capped physical witness and the southern position control. The longest unchanged leading principal block between adjacent factors had width zero on both. Whole-input memoization therefore had a **0 ms ceiling** within the previously measured **39.887 ms and 1.767 ms** LAPACK budgets, respectively. The observer preserved every returned likelihood field byte for byte. [Audit receipt](measurements/solver-schur-reuse-audit.json) · [Observer](solver_schur_reuse_audit.py) · [Archived phase clocks](measurements/solver-wide-private-blocks.json)

| Captured witness | Shared dimension | Factorizations | Group precisions changed every transition | Touched shared columns | Exact rank of every Schur update |
|---|---:|---:|---:|---:|---:|
| DS30-0008 position | 134 | 257 | 111 / 111 | 134 / 134 | 134 |
| Southern containing position | 74 | 39 | 25 / 25 | 74 / 74 | 74 |

All transitions touched the complete shared support even with zero changes in prior precision. The exact binary64 lower triangles passed full-rank certification on all **256 physical and 38 southern** differences. Each entry was reduced as a dyadic rational modulo the odd prime 65521 before subtraction. Full modular rank proves full rational rank of the symmetric input to the factorization, with no singular-value threshold. An exact low-rank update would have to cover the whole shared dimension on every audited transition. These are two ordinary kernel trajectories from saved detections. [Rank and support checks](measurements/solver-schur-reuse-audit.json) · [Component tests](../../../tests/pipeline_eval/test_solver_schur_reuse_audit.py)

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

For the exact Schur audit, invoke `-m reports.ALGO08.single-core-2x.solver_schur_reuse_audit STOCK_BINARY NEW_OBSERVER NEW_RECEIPT PHYSICAL_WITNESS SOUTHERN_WITNESS` under the same environment and lock. Both witness paths use `sample-01.npz` in their respective saved capture directories.
