# Conditioned frame-budget prototype

This bounded variant starts from `limited-complex-v2`.  It changes only the
frame aggregation inside `full_conditioned_scores`: `LEO_CONDITIONED_FRAME_BUDGET`
accepts 1, 2, 4, or 8; an unset or invalid environment value uses the compiled
default.  A default of zero uses every valid frame.  Valid frames are first
collected for each call, then selected across their span: one frame uses the
midpoint; larger budgets include both endpoints.

The same chosen frames feed the FP32 CZT screen and each FP64 near-maximum
recheck.  Frequency hypotheses, screen guard, recheck rule and the 16-frame
final GLRT are unchanged.  The variation is a scientific approximation and
requires an output audit before use.

`build_conditioned.py` produces host, ASAN/UBSAN and ARM cross-build artifacts
under `builds-conditioned/`.  Host and sanitizer component tests run during
the build; ARM is only cross-compiled.  `audit_conditioned.py` verifies binary
hashes, intended compile defaults, test execution and byte equality of the
final-GLRT and boundary-policy source regions against `limited-complex-v2`.
