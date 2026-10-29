# Causal graph fast-position production worker

The production model `algo02-causal-family-v1` is the previously evaluated
ALGO02-v1 composition, qualified causal signed orbital-phase means, and
equal-assignment-prior satellite-family comparison. It is a deployment name,
not a new scientific ALGO promotion. The rejected ALGO04 recovery and later
CH5–8 acquisition experiments are excluded.

The worker consumes the existing `FastScanStore` public GLRT export. It finds
alias-aware polynomial graph tracks with the exact frozen configuration in
`deploy/config/fast-graph-tracklets-v1.json`, estimates radio noise, constructs
this scan's causal orbit bank and earlier TLE history, and runs discovery and
paired c=0/fitted-c inference. Linear tracks provide predictive evidence and do
not calibrate the receiver. Every numerical run starts at east/north zero in
the original 25×25 km box centered at 37.906°, −122.545°. This center is a
deployment region, not an evaluation coordinate or a global search.

Only TLE versions published and having epochs before the scan cutoff are
eligible. All source candidate sets are generated from the regional causal
catalogue. Signed means must qualify on earlier TLE transitions. The final
family hypothesis is selected by the existing corrected normalized c=0 loss,
with the same identities, aliases, masks, other priors and budgets for both c
arms. Fitted-c is the published position; the c=0 position remains in every
successful terminal. The original frequency residual and predictive phase
gates are retained. Curved-only fallback stores its five-round phase-change
diagnostic without inventing a new acceptance gate. This method does not claim
the strict stationarity contract of the older shared-q estimator.

Every input/model digest has a separate immutable attempt namespace:
`/srv/bulk/leo/fast-scan-graph-position-v1/algo02-causal-family-v1/jobs/`.
An output directory is never reused for numerical inference. A watcher restart
can recover a completed terminal; interrupted/failed attempts remain visible
and are not automatically retried. The worker retains its input copy, graph,
TLE provenance, full numerical outputs, paired terminal, logs and per-process
read receipts. Read guards reject unrelated corpus/research/GPS/result inputs.
No radio, PostgreSQL connection or QNAP access is used by localization.

One worker processes the newest pending export first, with one BLAS thread and
a 1,200-second whole-job cap. The supervisor terminates the entire subprocess
group at its deadline; systemd uses `KillMode=control-group`. Missing curvature,
missing orbit history, rejected residual fits and runtime caps are explicit
unavailable/failed outcomes, never successful partial positions.

## Release and qualification

Stage only an exact committed full SHA using `tools/stage_fast_graph_release.py`.
The default invocation prints a plan. `--execute` copies the committed source,
an explicit CPython 3.12 runtime and uv, installs the hash-locked numerical
dependencies and imports the worker from its final path. The release lives at
`/opt/leo-fast-graph/<full-sha>` and is root-owned. A release with `.incomplete`
must never be selected. Runtime reads source from this release, including its
same-repository numerical tools; reference repositories and research directories
are not runtime dependencies.

Run component tests, then at least one complete real GLRT replay under the
`leo` account with the installed interpreter and source. Check both c arms,
original observation identity, causal input receipts, read receipts and terminal
qualification. Compare saved reference endpoints only after the fresh terminal
has sealed. A bounded operational replay is not new location validation.

Render `deploy/systemd/leo-fast-graph-position.conf` with the qualified release
path and install it as the `release.conf` drop-in for
`leo-fast-shared-position.service`. Preserve the previous drop-in in the dated
qualification directory. Run `systemctl daemon-reload`, restart only that unit,
and verify its actual command, active state and a completed new-model job.
Acquisition, GLRT processing, the API, existing shared-q outputs and historical
reports are not replaced by this worker cutover. The new model has its own
terminal contract and storage namespace; the older shared-q UI does not become
a graph-result viewer automatically.

Rollback restores the preserved drop-in, reloads systemd and restarts the same
unit. It does not delete any result or recording. Direct `main` publication
records source and the separate deployment receipt; a Git push alone is never
treated as a deployment.
