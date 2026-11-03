# Original production cold replay: read-only feasibility audit

No pipeline was launched for this audit. Sources inspected are the pinned live
`leo.cli.shared_fast_position` / `leo.application.shared_fast_position` modules,
the public `TleArchiveReader`, and the saved replay/local-segment receipts.

## Public entry point and bounded cost

The actual filesystem-only inference entry point is:

```python
from pathlib import Path
from leo.cli.shared_fast_position import run
result = run(training_input_path, fresh_isolated_output_directory,
             maximum_seconds=480, tle_root=Path('/var/lib/leo/tle'))
```

It accepts the exported TrackingInput JSON, reconstructs timing, prepares only
the supplied probes, builds a causal regional Starlink bank, runs discovery,
shape/bootstrap/source stages, and performs final shared-q fitting. It writes
immutable research receipts into the supplied fresh output directory and does
not publish through production storage. Existing attempts cannot be retried or
silently resumed. `prepare_views`, `build_regional_bank` and
`run_shared_position(..., receipts, maximum_seconds=...)` are the component
entry points when an explicit read-only TLE provider policy is needed.

The unmodified source policy is `generic-cold24-shape3-fresh-six-ab-v1`:
24 hierarchical points, 240-second discovery slice, three 20-second shape
proposals, six fresh sources, five-second bootstrap slices, source fits bounded
to 20 seconds/2000 actual calls, and final fits bounded to 65 seconds/5000 calls.
`run_shared_position.stage('discovery', 240, ...)` reserves a further 130 seconds
for finals before admitting discovery. Consequently an unmodified whole-run
allowance at or below 370 seconds, even before bank/preparation time, cannot
admit discovery. A faithful 120–300 second whole-pipeline replay is not available
merely by lowering the public CLI argument. Individual optimizer slices stay
below 120 seconds.

| Saved attempt on S01 | State | Elapsed (s) | A/B/shared optimizer calls | Counted A/B/shared objective calls | Final candidates |
|---|---|---:|---:|---:|---:|
| Original capsule forward | complete | 324.55 | 22 | 11519 | 54 |
| Original capsule reverse | complete | 336.62 | 22 | 11940 | 60 |
| Local-segment v6 forward | complete | 405.85 | 10 | 6554 | 86 |
| Local-segment v6 reverse | complete | 403.69 | 10 | 6511 | 86 |

All used a 480-second overall allowance. These actual elapsed times do not
override the admission reserve. A single faithful attempt can be bounded at
eight minutes and has historically finished in about 5.4–6.8 minutes; it is not
a 1000-evaluation comparison. A multi-recording, both-direction, both-c-arm
campaign would be a different, much larger experiment and is not launched.

The terminal's exact cost counter explicitly excludes discovery, shape and
bootstrap. Copied original discovery receipts contain 72 view fits per fold,
with 23650/23085 reported solver evaluations and about 99/97 summed fit seconds.
v6 discovery receipts contain 27/24 fits, with 13696/13020 reported solver
evaluations and about 123/119 summed fit seconds. These differently scoped
counters must be reported separately rather than presenting terminal calls as
the whole algorithm cost. Source admission can close before all six proposed
sources run; unadmitted paths remain unavailable in stage receipts.

## The old folds are target-only exclusions, not full temporal halves

`three-track-recovery-replay-20261016/rerun_cold.py::prepare` reads the frozen
derivation's `withheld_original_rows`, maps them to entire
`(visit_index, receiver_id, probe_index)` groups, removes those probes and verifies
the derived-input digest. It is a byte-checked reconstruction of that historical
experiment, not a generic full-half splitter.

| Historical fold | Original observations | Removed target groups | Remaining training observations |
|---|---:|---:|---:|
| forward | 4797 | 63 | 4734 |
| reverse | 4797 | 66 | 4731 |

Training still spans nearly the full 300 seconds and includes other channels and
groups at times inside the withheld target halves. In contrast the current S03
test withholds all 1994 observations in a temporal half. The historical original
75/129 supported-label held matches cannot serve as its expected coverage or a
matched approximately-12% baseline. Those historical labels are not independently
verified satellite identities either.

The old local-segment v6 runner is additionally a changed source-generation
policy: 231/232 automatically extracted short proposals replace the original
bootstrap groups; batched orbit-shape queries use six samples per segment;
combined discovery fits increase from 5 to 15 seconds; discovery is shortened
to 180 seconds. v4 had unavailable combined-fit convergence; v5 converged
discovery but admitted no A/B source because the final reserve was exhausted.
v6 resolves those scheduling/numerical failures, reaches strict endpoints,
and still has zero of 129 held points assigned to supported training-selected
labels. It is neither an unchanged production initializer nor recovery proof.

## Requirements for a genuine new full-half replay

1. Derive a new public TrackingInput by filtering **every raw probe group** on
   the declared training side using timing/counter/support metadata. Do this
   before production preparation/reconstruction sees any held CFO. Preserve
   the original clock anchor/counter/RF authorities, record parent and derived
   hashes and all excluded group keys, and test that perturbing all held CFO
   leaves derived training bytes and fitting unchanged. Do not reuse the old
   three-target membership derivation or import any old selected position.
2. Rebuild candidate discovery from that input for a complete-pipeline test.
   This changes the fixed-bank comparison: the bank, bootstrap track inventory
   and discovery calibration are then genuinely training-derived. Pin the causal
   TLE digest/provider policy explicitly and retain provider provenance. The
   historical capsule pins Space-Track `c1341ed3...` (collected UTC ns
   1792166533595712561, verified through `TleArchiveReader.list_snapshots`),
   not the primary S01 `2439873f...` bank.
3. Provide a fresh isolated attempt directory and a declared 480-second
   whole-run cap. Report preparation, bank, discovery, bootstrap, source and
   final costs and all unavailable paths. Do not replace a failed discovery
   gate with a saved full-recording state. If a shorter component experiment is
   chosen, label its reduced discovery/source schedule as a changed policy.
4. Extend only the **training-selected satellite IDs** to the complete evaluation
   time domain using the pinned causal orbits and observation timing/RF metadata.
   The live regional bank covers observation min/max only plus 21 seconds;
   a bank built on a 150-second half does not cover the other 150-second half.
   `prepare_views` likewise builds 30-second clock nodes on the supplied
   observations. Frozen clock extrapolation outside that domain needs an
   explicit policy and complete output coverage; it cannot be hidden by a skip.
5. The public production pipeline hardwires fitted c in discovery/shape/shared
   fitting. A final matched c=0 continuation is conditional on that fitted-c
   source discovery and frozen contrasts, as the old experiment states. A
   complete c=0 source-generation experiment needs an explicit research arm
   through all relevant component fits. Do not call a conditional continuation
   an independently rebuilt zero-c cold pipeline or infer better localization
   from frequency J alone.

A bounded single-fold production replay is technically feasible. It requires
the new full-half derivation and the above evaluation-domain handling first;
none of the saved historical attempts answers that exact question. The current
neutral/paired/donor/grid prototypes should therefore remain clearly separate
from a replay of the original production source-generation procedure.
