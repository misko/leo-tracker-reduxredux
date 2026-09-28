# Frozen constant-frequency null ablation

Before this ablation's first fit, freeze a per-track mixture with prior mass 0.01 on a constant-frequency null and 0.99 on the original satellite mixture. Both use the same 100 Hz Student-t4 density and stationary training-profiled offset with the existing weak offset penalty. The satellite component retains full-catalogue normalization and the exact finite bank. The null has no position/timing dependence. Its mass is fixed, not learned from held windows or geographic error.

Run first `single-001` only, using the existing local three starts and total 180 objective-evaluation cap, 60 evaluations per start. Allow 300 seconds wall time within the coordinator's aggregate 600-second search/ablation lease. No source reads beyond the frozen numerical inputs. Use the same fast profiler and direct interpreter under the shared runner.

Report every start, convergence/boundary flags, train objective and per-track null responsibilities. Compare geography only after sealing predictions. A smaller residual or greater likelihood under this expanded model is not evidence of better positioning. The null is a generic constant-frequency alternative, not a complete model of interference or proof of source identity. Its prior is an explicitly exploratory modeling choice; DS7 is not an untouched holdout.
