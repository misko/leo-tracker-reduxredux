# Fine-frequency frame-budget prototype

This experiment caps only the corrected limited-complex-v2 fine-frequency
estimator. It retains every window and candidate, the conditioned boundary
fallback, and the unchanged final FP64 GLRT source.

`LEO_FINE_FRAME_BUDGET` accepts 1, 2, 4, or 8. Unset means all available
frames. Selected frames span the available sequence deterministically: one
frame uses the midpoint, two use both endpoints, and larger budgets use
integer-even positions including both endpoints. Invalid values fail before
input loading.

For the unchanged `low_precision/evaluate.py` CLI, each host/ARM build includes
`cohort_frame_full_*` and `cohort_frame_{1,2,4,8}_*` executables with the named
initial budget compiled in. The environment variable can still override that
initial value at runtime. Each emitted row records `fine_frame_budget`.

The component test exercises the all-frame default, budgets 1/2/4/8, exact
selected indices, 16-byte cache alignment, partial probes, and all four sample
rates. ARM artifacts are cross-build only and must be executed serially by the
experiment owner.
