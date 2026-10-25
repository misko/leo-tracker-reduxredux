# Replay and artifact map

The recorded outputs are immutable and the runner refuses overwriting them.
Do not rerun a scientific stage in this directory. Numerical replay in a new
directory is a new authorized bounded study, with fresh seals and preserved
inputs; it is not a retry of a failed endpoint. Existing code contains absolute
paths to the research corpus and repository. Published sources alone do not
include that corpus.

The original environment was the repository `.venv/bin/python` with NumPy,
SciPy and Matplotlib, plus the original feasible-recovery dependency directory.
The exact source and archived input bytes are bound by `protocol.json` and
`protocol_seal.json`; `freeze.py` hashes imported local numerical modules,
frozen scan files, causal histories, original baseline and accepted-ID ledgers.
It performs no scan propagation or position fitting.

Owned algebra tests (no scan propagation or position fits):

```bash
cd /home/mouse9911/gits/leo-tracker-reduxredux
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/tmp/algo03-feasible-deps:src:tools:/srv/bulk/leo/research/ds24-movement-policy-r01/recovery:/srv/bulk/leo/research/ds24-parent-orbit-uncertainty-r01/scientific \
.venv/bin/python -B -m unittest discover \
  -s /srv/bulk/leo/research/ds24-parent-orbit-uncertainty-r01/scientific \
  -p test_scientific.py -v
```

Nine tests cover old-column and 300-Hz constant indices, normalized zero-mode
VI equivalence, shared-family feature loading and zero variance, copied
conservative residuals, dense shared covariance/information monotonicity,
non-crossing triage criteria, expired budgets, both-arm ID preservation and
unclipped phase/Gamma validity. Initial test receipt is preserved; the only
initial harness error was a generic `diagnostics` import-name collision,
resolved before freeze with the unique `parent_diagnostics` module name.
`test_receipt02.json` and independent preflight record the passing suite.

`adapter.py` supplies both inference methods, explicit old/added coordinate
maps, conservative and literal gate views, full native GLRT denominator and
separate likelihood/accepted/raw-gate membership. `parent_diagnostics.py`
contains actual objective probes and the OLD-state information control.
`runner.py fixed` was run only after independent preflight. It saved:

- `fixed/<case>.json`: both-arm gradients, components, numerical checks,
  old/primary/refitted information and predeclared proxy quantities.
- `fixed/<case>_reference.json`: freshly replayed exact original reference
  summaries, complete accepted-ID coverage and likelihood ownership.
- `arrays/<case>_<arm>_fixed.npz`: OLD J/U/weights/prior, appended B, joint
  augmented design and both information matrices for independent dense replay.
- `fixed_summary.json` and `fixed_seal.json`: all four terminal statuses,
  cumulative scientific time, fixed Boolean triage and artifact hashes.

The same frozen runner's `fits` stage required a separately written coordinator
go binding protocol and fixed seal, after independent actual-context audit and
evaluator freeze. It used cold [0,0], five phase rounds and 48 iterations per
round, both c arms and methods, with no rescue. Each fit preserves:

- `fits/<case>/<method>/<arm>/epoch*.json` and `raw_endpoint.json`: every
  phase-refresh checkpoint before gates, absolute unclipped posterior phases,
  actual last phase changes, Gamma convergence and raw objective.
- `endpoint_arrays.npz`: full feature/coefficient/prior/Gamma/noise arrays,
  full and conservative residuals, predictive features/residuals and masks.
- `result.json`: conservative and literal full-mean summaries, exact original
  likelihood membership, complete and raw-gate coverage, and objective
  components evaluated at the same original phase reference for both models,
  in addition to each fit's own final-reference decomposition.
- `fits/<case>/result.json`: all methods/arms, any failures, both-arm
  convergence/qualification, original-ID preservation, postfit relabels and
  frozen hypothetical fallback. The operational source is always the original
  reference. Literal expanded postfit extension is unavailable rather than
  inferred through the incompatible legacy contiguous-mode layout.

`fits_summary.json` and `fits_seal.json` bind all terminal results. B's
`../audit/` contains independent source/math, actual fixed-state and terminal RF
audits. Geographic evaluation is a separate sealed report owned by the
coordinator/evaluator; this branch never calculates truth errors.

`report_rf.py` reads only sealed saved artifacts, checks their hashes, and
produces `rf_report/` with a full CSV, source-bound JSON and two static figures.
It performs no propagation, nuisance inference or position fitting. Its output
directory also refuses overwrite. The RF findings do not use a frequency-fit
improvement as evidence of localization improvement.
