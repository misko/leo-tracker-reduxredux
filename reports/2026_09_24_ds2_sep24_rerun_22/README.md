# DS2 September 24 successor driver

This directory is a fresh, parameterized successor path. It does not reuse or
write into the completed 20-session reports. `successor_driver.py` first
validates a sealed whole-corpus manifest and every receipt-bound causal cache,
then creates a new report root containing a portable plan, per-task inputs, a
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

This is a planner plus a portable executor, not a full successor-rerun
implementation. Planning creates no model output. Portable execution is an
explicit later action using the same arguments with `--mode portable --execute`;
it refuses to replace any task result. The generated follow-up contract records
the cap-800/rate screen, session-scale/residual diagnostics, and shared-NORAD
accounting as pending exact-gated successor adapters. The legacy joint-session
L-BFGS-B arm remains recorded as rejected and is never scheduled.

The cone branch admits only manifest sessions with an explicit capture-time
geometry binding. Its plan always contains both provisional RX-to-slot
mappings (`[0, 1]` and `[1, 0]`) and all four fitted cone families. It requires
a fresh receipt-bound geometry export before any cone computation.

`postseal_evaluation.py` is the only program here that accepts reference
coordinates. It refuses them until the successor portable execution artifact
is complete and digest sealed.
