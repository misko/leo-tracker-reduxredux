# DS2 September 24 successor driver

This directory contains the completed, parameterized 22-capture September 24
successor evaluation. It does not write into the completed 20-session reports.
`successor_driver.py` validates the sealed whole-corpus manifest and every
receipt-bound causal cache, then creates a portable plan, per-task inputs, a
geometry/cone admission plan, and model accounting.

The portable task name is generated from manifest membership: a 22-session
manifest produces `joint-all22__…`. Every joint task uses all complete
sessions. This successor has no train/validation/test split; reference
evaluation is external and post-seal only.

```bash
.venv/bin/python reports/2026_09_24_ds2_sep24_rerun_22/successor_driver.py \
  --manifest /path/to/sealed-successor-manifest.json \
  --cache-root /var/tmp/leo-ds2-sep24-rerun-22-cache \
  --output-root reports/2026_09_24_ds2_sep24_rerun_22/output
```

Planning creates no model output. Portable execution is an explicit action
using the same arguments with `--mode portable --execute`; it refuses to
replace any task result. The completed run contains 110 single-capture tasks,
six all-22 joint tasks, two joint refinement stages, and the exact-gated
cap-800/rate, session-scale/residual, and shared-NORAD diagnostics. The legacy
joint-session L-BFGS-B arm remains recorded as rejected and was not scheduled.

The cone branch admits only manifest sessions with an explicit capture-time
geometry binding. Its plan always contains both provisional RX-to-slot
mappings (`[0, 1]` and `[1, 0]`) and all four fitted cone families. It requires
a fresh receipt-bound geometry export before any cone computation.

`postseal_evaluation.py` is the only program here that accepts reference
coordinates. It refuses them until the successor portable execution artifact
is complete and digest sealed. The final findings, digest-bound comparison,
and visualization are in `REPORT.md`, `evaluation.json`, `comparison.csv`, and
`postseal-comparison.png`.
