# Qualified DS21 A/B/C runtime facade

The new facade changes validation transport, not scientific models, seeds,
selection, or numerical budgets. The genuine original-v2 and coverage-v1
readers first qualify their own parent authority. The distinct runtime protocol
then binds those exact scientific protocols, source archives, input bytes, and
immutable case-specific directory inventories. Runtime checks reject additions,
missing files, and changed bytes; they avoid repeating recursive source AST
discovery inside the fit deadline. No existing scientific source or namespace
was edited, and no module globals are patched.

Implementation commit: `8c981b87d`. The component suite passed **15 tests in
59.38 seconds**; Ruff passed. Tests cover actual core/model construction and
receipt serialization, exact call inventories, source additions, ancestor
overlap, failed/orphan qualification, preserved failed attempts, six physical
lifts and 54 original starts, metadata-only recovery, and a 12-unit/7-selector
terminal. Synthetic fit payloads test receipt plumbing; the corpus proofs below
provide the numerical execution evidence.

The immutable policy retains fitted c, 20 seconds and 600 iterations per call,
six starts, and the 25 km local disk. Preparation has its own measured 30 second
bound; whole A units retain 90/105/110 second internal/TERM/KILL limits, and B/C
units retain 165/175/180 seconds. Failed attempts are retained without retries.
Qualification requires a durable exclusive launch, complete termination,
source binding, and zero predictor/objective/optimizer counters before fitting.

| Scientific parent | Authority files/directories | Before check | Preparation | After check |
|---|---:|---:|---:|---:|
| original-v2 DS21-003 | 1,677 / 8 | 0.105493 s | 20.648604 s | 0.096793 s |
| coverage-v1 DS21-005 | 4,418 / 9 | 0.182239 s | 18.572763 s | 0.218023 s |

Mean authority check time is **0.150637 seconds**. All four checks and both
preparations passed without scientific evaluations. The respective runtime
closures contain 415 and 419 source files.

The two failed original paths were recovered by metadata only:

- Original-v2 DS21-003 A-2 binds supervisor-003 job-0066's 105 second timeout,
  its launch, and all three matching stationary call triples.
- Coverage-v1 DS21-005 A-0 binds supervisor-003 job-0076's failed outer attempt,
  its launch, and all three matching stationary call triples.

Each recovery reused three calls and performed zero new optimizer, predictor,
or objective calls. Recovery checks fitted-c/20-second/600-iteration options,
proposal center and start, stationary flags against the unchanged validator,
the original low initialization, and own-path low/high/final dependency fields.
Original failed receipts remain unchanged. Lost post-fit diagnostics are
explicitly unavailable, rather than reconstructed through scientific calls.

Fresh namespaces are `local/model-a-pipeline-before-003-v1` and
`local/model-a-pipeline-coverage-005-v1` beneath this report directory. Their
protocol hashes are, respectively,
`4bf74c31bb584f25fb54b95a774ea5de8a43e86d758b863ebb1b10f667c3d24a`
and `38b46e431c4f01b94ad72019a4c6454d674116ac31c275488c488dbc9802cefe`.

Six previously unattempted proof units were launched concurrently with single
BLAS threads: original-v2 A-3/B-all/C-all and coverage-v1 A-1/B-all/C-all.
Their outcomes and receipt bindings are recorded in the accompanying JSON.

| Parent | Unit | Whole runtime | Stationary / attempted | Selected start | Training objective | Training RMS |
|---|---|---:|---:|---:|---:|---:|
| original-v2 DS21-003 | A-3 | 37.268 s | 0 / 1 | unavailable | unavailable | unavailable |
| original-v2 DS21-003 | B-all | 63.552 s | 5 / 6 | 0 | 28,788.051021 | 79.646979 Hz |
| original-v2 DS21-003 | C-all | 116.902 s | 5 / 6 | 5 | 27,019.323246 | 92.882310 Hz |
| coverage-v1 DS21-005 | A-1 | 41.199 s | 3 / 3 | 1 | 24,552.140535 | 114.557110 Hz |
| coverage-v1 DS21-005 | B-all | 49.849 s | 6 / 6 | 4 | 21,245.557258 | 78.813476 Hz |
| coverage-v1 DS21-005 | C-all | 92.943 s | 6 / 6 | 3 | 20,585.580089 | 102.517446 Hz |

All six units returned exit code zero and retained complete source-bound outer
terminations. There were **28 new calls, 25 stationary**, plus the six separately
recovered stationary calls. Original-v2 A-3's low stage had stationarity
0.00128665 and was rejected by the unchanged scientific validator; its high
and final stages were correctly omitted. Original-v2 B start 1 and C start 4
also retained their nonstationary outcomes. These are scientific failures,
not runtime or serialization failures. No attempt was retried. Original-v2 C
start 3 reported 20.024 seconds for the unchanged 20-second solver option,
including its return overhead; the whole-unit bound still passed.

No reference evaluation was performed: each case still requires its full
12-unit matrix to seal. Frequency scores below are training evidence only;
this runtime qualification makes no position-accuracy claim.

The CLI exposes `freeze`, `initialize`, `qualify`, `recover`, `reuse`, `run`,
`seal`, and `evaluate`. Existing complete scientific units require explicit
`reuse`; failed complete-call paths require explicit `recover` with the bound
scheduler termination. `run` rejects attempted original units and orphan or
failed runtime attempts. `seal` requires all twelve units; `evaluate` can join
the configured development reference only after that terminal exists.
