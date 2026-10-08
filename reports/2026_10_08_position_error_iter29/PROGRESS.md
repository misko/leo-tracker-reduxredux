# Saved continuation: unchanged reserved validation pending baseline completion

Goal lifecycle is active with no remaining-token limit. Do not mark complete:
independent validation, integrated deployment and live PNG verification of the
research candidate remain outstanding. Existing production deployments remain
unchanged.

## Completed evidence

- Iteration27 report `1c8e029fb`: all119 tighter-prior sweep complete. Select
  sigma0.25 by the frozen gates: fitted mean 1.001464 → 0.961650 km, p95
  2.139346 → 1.996970, worst 2.762679 → 2.750798. Other tested priors fail
  cohort/worst guards. All data here are consumed development, not validation.
- Iteration28 frozen source/protocol `b78cd015b`, report `0a730025b`: S41 and
  DS17-008 assembled final-stage canaries match frozen iteration27 exactly in
  both arms (vectors, clock arrays, objectives and errors). First RESERVED-004
  attempt failed because its standard baseline was pending. Preserve that
  failed result; no validation outcomes were opened.
- Iteration29 numerical completion source/protocol frozen as `0da476d0a`.
  Same candidate, split, priors, fit budgets and gates. `summarize.py` is prepared
  reporting code; do not execute until outcomes are available unless explicitly
  reporting missingness.

## Currently running operation

Supplemental **unchanged standard** Hard60 baseline analysis for development
recording `scan-fw-c17fbfacad538641`, using the deployed worker source
`/opt/leo-tle-review/8f54778f9/worker/src` and production Python
`/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python`.
The configuration hash matches the deployed Hard60 configuration
`d1524c45e6e702008221d941240e7a0ac26f13feac87fef73e83f04c9c0a80f6`.

The first 500-second slice completed with `pending` and checkpoint phase
`sha256:faf70f935e8a26a3f07f3a2a84a51589045da0397a4e6e71d2ca51c91486b7b6:point:-87.5:-82.5:association`.
It exited normally (old tool handle67625 terminal). A second slice is running
under **tool process handle27050**; poll it before starting another process.
Each invocation has a 500-second internal budget and a 540-second outer timeout.
It resumes immutable checkpoints instead of starting the grid over.

Command, run from `/home/mouse9911/gits/leo-hard60-default`:

```sh
sudo -n env PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/opt/leo-tle-review/8f54778f9/worker/src \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  timeout 540 \
  /opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python \
  -m leo.cli.regional_position --maximum-seconds 500 scan-fw-c17fbfacad538641
```

The existing production worker was not stopped. It was observed in a different
TLE-position component; our supplemental regional process obtained the correct
regional writer lease. Do not kill production workers or duplicate a currently
active regional writer. No RF acquisition was started.

## Next actions

1. Finish the bounded standard baseline slices. Public availability-only checks
   already show RESERVED-001/002/003 baselines complete; their errors were not
   inspected. RESERVED-004 is the sole pending prerequisite.
2. Once its baseline is published, run `iter29/complete.py RESERVED-004` under
   the production environment above (omit `timeout`/CLI arguments). This loads
   through public ports, preserves additional regions, runs frozen upstream
   joint fits, then matched control/slope fits. Do not alter frozen source.
3. When its result has status `complete`, run RESERVED-001/002/003 through the
   same script. These independent evaluations can run concurrently. Do not tune
   based on development or validation errors. Keep all assigned scans/failures.
4. Run `iter29/summarize.py`, inspect gates/plots and c locks; publish README,
   results and figures with integrity hashes to remote main. Retain iteration28's
   initial availability failure and label this a completion, not an unblemished
   first execution. Three validation scans are a small sample.
5. If qualified, implement a versioned runtime successor per iteration27
   integration notes, with component tests and a cold integrated execution before
   deployment/WebUI verification. If not qualified, preserve the failure and
   diagnose it as consumed development before any new independent validation.

Use `git push origin HEAD:main`; pushing reports does not deploy. Preserve all
unrelated dirty files and untracked caches. QNAP stays read-only. All numerical
comparisons retain matched zero-c/fitted-c ablations. The original 153-km DS17
failure is 2.616195 km under the selected prior; its 0.75-prior 0.829848-km result
must not be cherry-picked into an operational policy.
