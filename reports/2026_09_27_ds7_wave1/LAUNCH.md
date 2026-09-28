# DS7 evaluation launch

User authorized execution of the prepared SOL evaluation plan on 2026-09-27. This directory records the bounded first wave and decisions about dependent directions. The frozen DS7 corpus and prepared plans are unchanged.

The bounded wave is complete. See [RESULTS.md](RESULTS.md) for scored predictions, failed attempts, stop/hold decisions, runtime cleanup repair, validation and next priorities. No worker or scientific evaluation remains running for this wave.

## Wave 1 assignments

| Direction | SOL agent | Owned outputs | Initial resource lease |
|---|---|---|---|
| A: corrected baseline and controls | `ds7_baseline_execution` | `baseline/`, baseline adapter/exporter, baseline tests and ready arm | One compute process, BLAS 1 thread, at most 4 GiB incremental RAM; cached products only |
| B: causal orbit inventory | `ds7_orbit_execution` | `orbits/`, orbit inventory tool and tests | One process, at most 2 GiB incremental RAM; metadata/archived orbit inputs only |
| F: CFO panel preparation | `ds7_cfo_execution` | `cfo/`, panel tool and tests | One process, at most 2 GiB incremental RAM; metadata/cached products initially |

All use `gpt-5.6-sol`, with no inherited conversation. No worker may spawn agents. The coordinator owns shared runner contracts, resource coordination, scoring and advancement decisions. Existing unrelated research processes are left untouched; initial host observation showed approximately 32 GiB available RAM and substantial CPU activity, so concurrency and I/O remain conservative.

The first adapter execution is the frozen `single-001` transport smoke, capped at 60 seconds. The scientific panel is `single-001`, `prefix2-01`, `prefix4-01`, `group8-01`, capped at 60 seconds per unit and 300 seconds total adapter execution. Input preparation and hashing are separately bounded by the worker lease; no multi-hour campaign is permitted. Unsupported or unqualified baseline results stop scientific expansion rather than triggering a silent budget increase.

No raw-IQ reader is leased initially. A CFO worker may propose one narrowly scoped existing-IQ test, at most 512 MiB total payload read and 120 seconds compute; the coordinator records the specific lease before any such read. No fresh RF or source-store mutations are authorized.

## Shared inputs and evaluation boundary

Workers use the generated reference-free plans under `reports/2026_09_27_ds7_evaluation_setup/plans/`. They do not inspect DS7 pose/full manifest or reference-scored outputs. Source products are accessed through public read-only ports and must match the plan's source-manifest hashes. Inherited DS6 priors and candidate conditioning must be declared; a different estimator cannot be substituted and called the corrected baseline.

The coordinator evaluates sealed predictions only after the experiment configuration, inputs, and model outputs are fixed. Scores are not returned to workers for tuning. Scientific variants need a frozen baseline observation/candidate interface first. Directions C (receiver clock), D (orbit hierarchy), and E (association/search) advance only after their stated prerequisites are available; preparatory audits can run independently.

## Preflight

- DS7 loader: 88 exact recordings, 194,934 visits and eleven complete groups of eight.
- Existing infrastructure component suite: 19 tests passed at launch.
- Host hardware and production services remain unchanged.
- Scientific outcomes, blockers and gate decisions will be summarized in `RESULTS.md` with links to direction receipts.

## Runtime repair before scientific execution

The runner formerly resolved the interpreter symlink to its base executable, which would discard a selected virtual environment and its scientific dependencies. It now preserves the absolute virtual-environment entry-point path while hashing the executable bytes. A regression test verifies the invoked path. The shared suite now has 20 passing tests. `runner-repair.json` binds this pre-execution repair; the original launch receipt remains unchanged.
