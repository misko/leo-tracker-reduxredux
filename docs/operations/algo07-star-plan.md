# ALGO07*: consolidate production, then optimize under an equivalence gate

Status: implementation started, November 4, 2026, following the explicit goal
to implement and optimize ALGO07* with DS26 equivalence checked at each iteration.
Existing production remains the reference. ALGO07* is a research implementation
identifier, not a new scientific algorithm version. Production deployment requires
the qualification evidence below; the initial coordinator is research-only.

## Objective and scope

Produce the same scientific result as the complete production ALGO07 chain,
using one logical scan job, while removing redundant orchestration and repeated
calculations. Compare the candidate against freshly executed, pinned production
workers on identical inputs before promoting any optimization.

Current dependency order:

```text
Capture -> native GLRT -> graph / causal preparation -> initial localization
        -> predictive recovery -> numerical recovery -> conditional gaps
        -> additional-family recovery -> guarded reassociation -> publication
                                  ALGO02 through ALGO07
```

These are sequential inference dependencies, not independent alternative
analyses. The ALGO07 worker explicitly requires a completed ALGO06 incumbent,
checks its endpoints/objectives/owners and uses it as its rejection fallback.
Removing a recovery pass can change later candidates even if that pass did not
change the final answer on a particular scan.

ALGO07* initially starts at the **public native GLRT evidence** and ends with
the final standard position, its scientific evidence and eight Web UI figures.
Capture and native GLRT stay unchanged and retain separate timing spans. An
end-to-end smoke test uses the same sealed IQ recording with the same native
implementation for both paths. No new RF collection is needed.

The first candidate must execute every existing scientific pass in the same
order, with the same priors, candidates, starts, aliases, phase quadrature,
random folds, solver settings, tie-breaking and acceptance policy. It must not
use reference position, scan ID or known error to control inference.

## Architecture: one job without an unsafe all-at-once rewrite

One coordinator owns scan admission, a private workspace, stage checkpoints,
deadline handling and final atomic publication. Stages consume explicit evidence
and incumbent ports, not upstream private storage directories or ORM models.
Numerical components remain free of database, HTTP, CLI and concrete storage
imports. Existing adapters keep working for rollback and reference execution.

Start with **one coordinator and the existing isolated worker processes**.
Removing separate queue/discovery cycles does not require changing numerical
code or merging Python environments. Production currently pins different
implementation versions and helpers across stages: importing everything into
one interpreter immediately could silently change a stage's arithmetic or
module bindings. Consolidate workers into shared components only after each
extraction passes the same stage-level equivalence suite.

The coordinator retains a complete, validated scientific checkpoint after each
stage. A bounded stage failure follows that stage's original fallback behavior;
it must not erase an earlier accepted recovery, publish a partial candidate or
substitute a different error-handling policy. On restart, verify checkpoint
bindings and resume from the last completed stage.

An immutable per-scan evidence bundle should include:

- Native observation IDs, scores, channel/RX/RF metadata, times and aliases.
- Track graph and polynomial membership produced by the unchanged graph pass.
- Exact causal element records and history selected under the original rules.
- Noise and receiver-calibration inputs, configuration and implementation pins.
- Incumbent ownership and both-arm state at each internal stage boundary.

Availability and cutoff semantics are part of the bundle. Freezing an archive
must not silently give the candidate records that the reference did not receive.
Do not change stage-specific catalogue age limits by replacing all catalogues
with an undifferentiated shared bank.

## Equivalence contract

Use a comparison manifest with a strict allowlist of operational differences.
Timing, process IDs, workspace paths and implementation provenance may differ;
those fields must still be validated as well-formed and correctly bound. Do not
recursively ignore generic field names or discard entire metadata objects.

| Evidence | Required agreement |
|---|---|
| Native GLRT input | Identical observations, scores, aliases and invalid-window accounting |
| Graph / polynomials | Identical track IDs or a verified identity mapping, memberships, coefficients and splitting decisions |
| Satellite preparation | Identical causal records, order, exclusions, history and candidate sets |
| Every recovery stage | Identical nominations, eligibility, predictive folds, gate outcomes, accepted/rejected changes and fallback reasons |
| Ownership | Exact observation-to-satellite maps in both arms; no duplicates or lost points |
| Fits | Exact endpoint, objective, nuisance, phase, residual and saved optimizer values under the pinned environment |
| Final policy | Exact retained model, reassociation choice and failure/completion state |
| Presentation inputs | Exact predictions, residual arrays, curves, grid scores, path and final error values |
| Artifacts | Eight valid, correctly bound PNGs plus manifests and grid/path sidecars |

Begin with exact scientific-value comparison and preserve array dtype, shape
and ordering. Do not select a numerical tolerance after seeing a difference.
A contraction-order or solver change that needs a new tolerance is a separate
proposal and does not pass this strict ALGO07* gate merely because the endpoint
looks unchanged. Existing documented historical tolerances remain distinguishable
from exact parity; use the current pinned production execution as the oracle.

PNG bytes should be compared when renderer, libraries, fonts and metadata are
identical. Rendering-only differences can be reviewed separately, but the data
shown, coordinates, error annotations, native owners and completeness must agree.
Never demand byte-identical manifests whose legitimate operational timings differ.

Both **c=0 and fitted-c** are mandatory, with matched observations, catalogues,
priors and budgets. Report RF objective/residual agreement separately from
geographic error. Evaluation coordinates enter reporting only.

### Deadlines need an explicit policy

Faster code can finish a search that production times out. That is a real change
in the delivered answer even with identical numerical routines. Preserve
per-stage deadlines and semantic work limits initially; never replace them with
an arbitrary shorter global deadline or reallocate unused time between passes.
The research harness runs bounded stage invocations and checkpoints long scans
instead of creating an unbounded multi-hour job.

Separate comfortably completed equivalence cases from deadline-sensitive cases.
For the latter, test deterministic injected cancellation/failure at matching
logical boundaries, verify fallback equivalence and report actual wall-time
outcome differences explicitly. No claim of universal exact equivalence is
possible for all wall-clock interruptions. A timeout becoming a successful fit
requires review; it cannot be counted as an unchanged-result speedup.

## Execution sequence and exit criteria

| Phase | Work | Required exit evidence |
|---|---|---|
| 0. Freeze production | Inventory each installed stage, Python/NumPy/BLAS/native libraries, thread limits, configs, entrypoints, contracts and budgets. Export through public ports. | Reproducible stage graph, hashes and provenance; no reference answers exposed as candidate inputs |
| 1. Establish oracle and comparator | Fresh production replay in isolated outputs; repeat to test determinism; record stage snapshots and compare all scientific evidence. | Repeatable reference; comparator deliberately detects changed owner, gate, endpoint, TLE, alias and missing artifact |
| 2. ALGO07*-0 coordinator | Run the pinned workers in the same order under one scan job, retaining their original isolated runtimes and public adapters. No science changes. | Every internal stage and final result agrees; interruption/resume and concurrency tests pass |
| 3. Remove transport overhead | Replace redundant export/copy/decode cycles with narrow evidence ports and validated immutable bundles; remove redundant polling between stages. | One modification per trial; exact stage/final parity and a measured wall/CPU/I/O benefit |
| 4. Share prepared calculations | Extract genuinely identical geometry, calibration or matrix preparation behind pure interfaces; cache only exact repeated requests. | Exact intermediate arithmetic, endpoint/owner parity, bounded memory and mutation/copy/restrict tests |
| 5. Trim proven redundant work | Remove work with a demonstrated data-flow equivalence, or short-circuit a rejection only when the exact existing rejection condition is already known. | Proof of condition plus adversarial tests and full paired replay; retained evidence remains sufficient for audit |
| 6. Cohort qualification | Fresh paired runs over the predeclared available DS26/27/28 cases and held-back recent fast scans. | No unexplained scientific differences; complete denominators, failures and unavailable cases; runtime distributions |
| 7. Shadow and promote | Run on newly sealed recordings in separate namespaces, compare, then perform a guarded rollout. | Identical science and artifacts, demonstrated runtime/throughput gain, rollback tested, explicit deployment decision |

The first concrete deliverable is **ALGO07*-0 plus the equivalence report**, not
an aggressively optimized solver. If it fails, identify the first divergent
stage before making any performance changes.

### Trimming rules

Safe candidates to investigate: already-validated immutable data decoded twice;
orbit states recomputed for identical bank/time/phase requests; copied arrays
that no caller mutates; a calculation immediately replaced without being read;
independent repeated setup with the same numerical provider and operation order.

Not allowed in the exact track: skipping ALGO03–06 because they usually reject;
reducing satellites, tracks, phase samples or optimizer iterations; reordering
recovery passes; changing priors; selecting only one calibration arm; omitting
uncertain points; treating an approximate bound as an exact rejection proof.
Such changes can be evaluated later as a different scientific candidate.

## Benchmark population and timing

Every optimization iteration must compare all available DS26 fast cases against
fresh production executions. The initial November 4 public-port inventory finds
158 available native inputs among 159 fast members, plus 158 adaptive members
excluded from this fast-only work. The one fast member without a native run stays
in the denominator. Input availability does not imply a successful position fit.

The historical DS26/DS27/DS28 audit contains 175 paired cases / 350 arms (148
DS26, 13 DS27, 14 DS28), with 15 unavailable upstream cases at that time. Use it
to locate diagnostic strata, not to replace fresh inference or exclude currently
available DS26 cases. Broader cohorts and new-scan shadow validation follow the
mandatory DS26 gate. Re-inventory before execution rather than assuming historical
availability is unchanged.

Start with a small fixed set covering: baseline-only retention; accepted
recoveries at different stages; accepted ALGO07 reassociation; rejected
reassociation; one-family and expensive two-family fits; upper/lower edge;
missing/invalid causal propagation; and controlled timeout/failure. Sample
representative scans reproducibly within those strata and record the seed and
case assignments before tuning. Include the November 4 14:00:48 UTC scan as a
geometry-heavy diagnostic, without giving its ID special inference behavior.

Then run the available full cohort as bounded scan/stage jobs. Reserve a
reproducibly randomized group of recent scans before optimization and validate
newly arriving scans separately. Keep correlated recordings grouped; no temporal
holdout is to be represented as randomized validation. Any unavailable, failed
or timed-out reference/candidate remains visible in the paired denominator.

Measure separately:

1. GLRT-ready to scientific position; active work and handoff/queue delays.
2. GLRT-ready to all eight figures and atomic artifact manifest.
3. Capture start and capture finish to complete Web UI publication.
4. Per-stage wall time, aggregate child CPU, peak memory, bytes read/written,
   validation, copying, catalogue preparation, fitting, grid and rendering.

Time profiles and performance trials separately. Use unprofiled A/B and B/A
pairs with matching CPU/thread limits, input/cache conditions and budgets.
Record host contention; do not run baseline and candidate simultaneously for a
paired latency claim. Report median, p90, p95 and worst case, scan-level paired
deltas and outcome counts. Do not sum CPU seconds across workers as wall time,
or add nested stage totals. Never multiply independent component speedup ratios.

The measured example had 319.57 seconds of ALGO02–07 workers, around 90.94 seconds
of additional inter-stage intervals, and 42.70 seconds in the original figure
timer. Those intervals are opportunities, not promised savings. The final
ALGO07 geometry-heavy replay spent 37.18 cumulative seconds in phase-shifted
states and zero calls in the two-family kernel. Different scan classes need
different optimizations. No tenfold improvement is established by these data.

## Persistence, UI and rollout

Use a separate research namespace/run identity for ALGO07* until qualified.
Keep the public major-version contracts immutable. The existing ALGO07 terminal
contains nested incumbents: build its real evidence through the compatibility
adapter rather than inventing dummy historical results or removing required
fields. Keep candidate implementation identity in an explicit research receipt
or a supported provenance field. A new public contract requires versioning.

One final public completion may replace the need for separately scheduled public
intermediate jobs, but it must preserve scientific provenance and the evidence
needed by rendering, audit and recovery. Internal checkpoints are not optional
just because the Web UI only shows the final result. The UI continues to show
both-arm final errors using the confirmed evaluation-only reference.

Test crash recovery, duplicate submissions, concurrent ownership, corrupted
inputs, partially written figures, cache invalidation and output integrity.
Keep all old production binaries and artifacts available. Shadow runs must not
compete for scan ownership or overwrite the production answer. No acquisition
or active numerical worker is interrupted during rollout.

Promotion requires a complete evidence report, exact scientific comparisons
under the declared domain, useful measured latency/throughput improvement,
acceptable memory behavior and successful failure/rollback tests. If any scan
has an unexplained mismatch, retain current production and investigate it.

For each iteration publish code/tests, implementation pins, case inventory,
timing table/distributions, full parity receipt, discrepancies and a Markdown
report. Separate verified facts, optimization hypotheses and rollout status.

## Initial implementation work packages

1. **Oracle/comparator:** reusable typed stage snapshots and complete ownership,
   decision, numerical and artifact comparisons; no normalization of scientific
   values. Build before performance code.
2. **Coordinator/adapters:** one job and resumable stage graph using existing
   qualified subprocesses and narrow public evidence ports. Keep deadlines and
   fallback rules stage-local.
3. **Measured redundancy:** profile decoding/export/validation and orbit-bank
   reuse; implement one exact optimization at a time after ALGO07*-0 passes.
4. **Qualification/reporting:** small diagnostic suite, randomized representative
   set, full available cohort, then new-scan shadow comparison and rollback.

These packages describe execution order and ownership boundaries. The initial
implementation uses one bounded private smoke pair before cohort scheduling;
no background agents or production changes are required for that step.

## Current qualification checkpoints

The first complete private smoke pair is DS26-0002. These checkpoints are
separate: passing a later endpoint check does not waive an intermediate failure.

| Checkpoint | Current evidence | Next required action |
| --- | --- | --- |
| Frozen production inputs and implementations | Complete for the first pair, including a private read-only causal archive | Preserve these pins for the next comparator iteration |
| Coordinator execution | All six original scientific stages completed | Add representative accepted/rejected recovery cases after intermediate comparison qualifies |
| Final science | Both endpoints, ownership maps, association counts and residual metrics match exactly | Repeat across all available DS26 fast inputs |
| Process provenance | All 42 original/copied receipt groups match after verified PID and private-path mapping; 27 process identities per execution | Retain this check alongside file-link and scientific-value checks |
| Intermediate science and hash links | First case passes exact JSON/array comparison: 3,037 JSON documents, 15,955 verified links per side, all six public terminals validated | Extend the comparator to additional representative completed/fallback cases without relaxing scientific fields |
| Publication | Both controlled A/B and B/A pairs pass all eight PNGs and all 179 grid points; prior 179-versus-96 deadline-sensitive failure retained | Keep completed and deadline-sensitive outcomes separate during the cohort run |
| Speed | No controlled end-to-end improvement established | Sequential unprofiled A/B and B/A measurements after parity |
| Full DS26 and promotion | Outstanding; 158 available fast inputs and one missing native input | Complete the paired denominator before accepting an optimization |

The process comparator follows references to earlier process receipts instead
of stripping numeric filenames. It rejects missing child receipts, denied reads,
unknown receipt references, cyclic ancestry/dependencies and changed exported
bytes. Read sets, interpreter launches and parent/child structure must agree.
Its result explicitly does **not** qualify scientific values or artifact parity.
See the [process provenance report](../../reports/2026_11_04_algo07_star_process_provenance/README.md).
The [intermediate and controlled-publication report](../../reports/2026_11_04_algo07_star_intermediate_parity/README.md)
records the first case's completed comparison, its typed accounting rules, and
the unchanged failure under earlier wall-time contention. Neither report is a
full DS26 or speed qualification.

The first optimization to evaluate after the zero-change gate is transport:
remove a demonstrated repeated evidence export or decode through a narrow public
port. The smoke output contains about 1.5 GB of repeated logical file content,
but this is not yet a measured speed benefit. Keep numerical operations and
stage order unchanged. Then evaluate exact repeated geometry preparation.
Give each change its own implementation pin, tests, full DS26 parity receipt and
paired timing report; do not combine several unqualified changes into one trial.

References: [runtime benchmark](algo07-runtime-benchmark.md),
[current timing investigation](../../reports/2026_11_04_algo07_pipeline_profile/README.md),
[first full smoke comparison and its failed grid-artifact gate](../../reports/2026_11_04_algo07_star_full_smoke/README.md),
[evaluation-only figure configuration](standard-position-error.md).
