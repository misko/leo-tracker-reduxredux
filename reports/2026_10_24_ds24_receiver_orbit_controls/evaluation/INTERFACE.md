# Matched DS24 position controls

No geographic reference appears in the fitting harness. Each model runs separately, with all 24 cases retained. A case is eligible only through a frozen RF-predictive qualification manifest. A qualified model replaces the exact saved baseline pair only if both original curved/predictive gates, phase convergence and regional bounds pass. In-sample RF score does not select between noise/covariance models. Failed or ineligible trials retain the original baseline pair. Position evaluation belongs to the parent reporter after all RF manifests and outcomes are sealed.

The adapter exports `build(d, arm, reference, case)`, returning a problem compatible with the existing `fit` and `summary` functions. `d` contains the exact persisted cavity baseline inputs: `scan`, `node`, `keep`, `powers`, `model`, `means`, `entries`, and `arms`. It may clone scan noise or add declared nuisance features/correlations inside the returned problem. The harness asserts unchanged physical measurement factors, assignments, aliases, masks, powers, causal receipt and 25 km bounds. It checks that predictive observations never feed back into calibration. Do not mutate the original `d`; clone mutable scan/seed objects before changing noise/features.

For a per-observation noise replacement, clone `scan.fixed_window_noise` and replace its per-ID sigma map before constructing the curved and predictive problems. Both `p.point_noise` and predictive `linear_geometry` must consume that same map. Set the existing nonconstant-noise branch explicitly when needed; preserve time-only `scan.white` unless a separately declared covariance model changes its semantics.

Protocol schema (all paths absolute, all hashes SHA256, cases in exact existing cohort order):

```json
{
  "schema_version": 1,
  "model_id": "frozen_model_name",
  "cases": ["all 24 baseline common_cases in their saved order"],
  "eligible_cases": ["RF-qualified case IDs only"],
  "adapter": {"path": "/absolute/adapter.py", "sha256": "..."},
  "qualification": {"path": "/absolute/RF_selection.json", "sha256": "..."},
  "source_bindings": [{"path": "/absolute/model_inputs.json", "sha256": "..."}],
  "phase_rounds": 5,
  "position_steps": 48,
  "start_east_north_km": [0, 0],
  "adoption": "RF_qualified_and_original_paired_gates_else_baseline",
  "GPS_used": false
}
```

Run one isolated case with `matched_controls.py --protocol MANIFEST --case CASE`, using the existing repository environment, `/tmp/algo03-feasible-deps:src:tools` plus the adapter/harness directory on `PYTHONPATH`, and BLAS/OMP/MKL threads 1. The parent coordinates at most four concurrent workers. Each case has a 240 s hard cap; every arm starts at zero with zero phase reference, five phase rounds and at most 48 position steps. There are no new multistarts or gate-constrained rescue iterations in this control. Repeated runs require the identical protocol digest.

`models/MODEL/CASE.json` preserves all attempted arms, convergence, original objective replay, normalized RF loss/RMS changes, exact baseline binding and an explicit common policy source. The baseline is never reconstructed from historical ALGO02 or a stale context endpoint.
