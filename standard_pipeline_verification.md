# Standard GLRT64 Pipeline — Implementation Verification Ledger

Status: active implementation evidence. Acceptance criteria live in
[`standard_pipeline_plan.md`](standard_pipeline_plan.md); this ledger records
what actually passed. A checkpoint is marked complete only with its exact
commit, test command, result, and independent review.

## Reference fixture

| Field | Value |
|---|---|
| Session | `production-24h-20260819-01-trial-00000132` |
| Local source | `/srv/bulk/leo/recordings/2026/08/19/production-24h-20260819-01-trial-00000132` |
| Protected TEST root | `/srv/bulk/leo/test-corpus/trial-132-four-path-v1` |
| Manifest SHA-256 | `sha256:1712bf9293b684540824ad4adfe0764a3477d01d7da8fdb28398ae465076855d` |
| Inventory | 2 radio streams, RX0+RX1 per stream, 21 files |
| Logical size | 1,179,310,752 bytes |
| Verified payload | 18 chunks; 1,179,238,949 compressed bytes; 2,400,000,000 uncompressed bytes; 2 timelines |
| Duration/rate | 60 seconds per stream at 2.5 MS/s |
| Measured start skew | 1,425,210 ns |
| Phase coherence | `false` |
| Truth tier | candidate-only exploratory sky evidence |

The application and its tests treat `/mnt/qnap01` as read-only. The protected
test fixture is materialized locally under `/srv/bulk/leo/test-corpus` with
source and destination digests verified. Any additional QNAP archive copy is a
separate operator action; repository code must not perform it.

Independent read-only verification:

```console
uv run python -c 'from pathlib import Path; from leo.storage import RecordingStore; s=RecordingStore.open_read_only(Path("/srv/bulk/leo/test-corpus/trial-132-four-path-v1")); print(s.verify(s.inspect("production-24h-20260819-01-trial-00000132"))); s.close()'
```

Observed: `VerificationReport(... chunk_count=18,
compressed_bytes=1179238949, uncompressed_bytes=2400000000,
timeline_count=2)` and the expected manifest digest above.

The complete fixture is sealed read-only: directories, including the fixture
root and empty `spool`, are mode `0555`; regular files are mode `0444`.
Analysis writes go to pytest-owned temporary output roots and never into this
fixture.

### Operator-only QNAP archive materialization

Repository code and automated tests must not run the following procedure. If a
human operator elects to create the requested redundant archive, they may copy
the already verified local fixture and then independently verify it:

```console
src=/srv/bulk/leo/test-corpus/trial-132-four-path-v1
dst=/mnt/qnap01/mouse9911/leo-store/test-corpus/trial-132-four-path-v1
mkdir -p -- "$dst"
rsync -a --checksum -- "$src/" "$dst/"
find "$dst" -type f -exec chmod 0444 -- {} +
find "$dst" -type d -exec chmod 0555 -- {} +
uv run python -c 'from pathlib import Path; from leo.storage import RecordingStore; s=RecordingStore.open_read_only(Path("/mnt/qnap01/mouse9911/leo-store/test-corpus/trial-132-four-path-v1")); print(s.verify(s.inspect("production-24h-20260819-01-trial-00000132"))); s.close()'
```

This is deliberately an operator action: the application does not create,
delete, move, rename, or chmod anything beneath `/mnt/qnap01`.

## Standard-v2 science slice receipt

The additive v2 implementation exposes pure component boundaries for one-RX
selection, exact probe scheduling, power, waterfall, bounded multi-candidate
pilot scan, degree-1/2/3 trajectory fitting, trajectory feedback, terminal path
reporting, radio reduction, and paired-radio reduction. Existing schema-1
Starlink trajectory feedback documents retain their published winner-only,
run-bound shape. New reusable v2 scientific documents omit run, job, scope, and
pipeline-release membership fields.

Focused component gate:

```console
uv run pytest -q tests/analysis/test_standard_pipeline_science.py tests/analysis/test_standard_multi_candidate.py tests/analysis/test_trajectory_feedback_stage.py tests/analysis/test_pilot_trajectory_bank.py
```

Observed: `15 passed in 1.10s`. This includes two crossing candidate basins,
deterministic rank/truncation, exact v1 wire regression, stable v2 bytes under
two different run identities, linear/quadratic/cubic fitting, uncalibrated-prior
fail-closed association, and pure deterministic radio/pair reducers.

Bounded real-IQ benchmark gate:

```console
/usr/bin/time -f 'WALL_SECONDS=%e MAX_RSS_KB=%M' uv run pytest -q -s tests/analysis/test_standard_real_corpus_e2e.py::test_trial132_one_path_one_coarse_window_benchmark_smoke
```

The pre-optimization receipt on 2026-08-19 was `20.205403713 s` for the science
call and `24.13 s` for pytest including full fixture verification, at `358988
KiB` RSS. Its deliberately simple four-path/twice extrapolation was
`9698.59378224 s` (about 2 h 41 m 39 s).

Commit `7fa2ffb` freezes the complete 368,432-byte pre-optimization one-second
output at
`corpus/goldens/trial-132-standard-v2-one-second-frozen.json`, SHA-256
`669a0686d7ec5d3a71c2749f42250be4a03479fa11dd19fdf03dd854ff8c1605`.
Every one of its 9,739 floating fields is compared to optimized output at the
reviewed absolute/relative tolerances; shape and non-derived fields remain
exact. The observed optimized science call was `3.888714383 s`; pytest plus
fixture verification was `7.79 s`, with `401196 KiB` maximum RSS. This is a
`5.20×` per-path science speedup. The host was simultaneously running eight RF
soak workers and an md127 resync, so these wall times are interference receipts,
not quiet-host release distributions.

The complete four-path/two-radio/pair analysis was then executed twice from raw
IQ in two isolated processes and create-only temporary output roots. It finished
both scientific runs in `11:30.70` wall (`3159.14 s` user, `525.95 s` system,
`533%` CPU, `/usr/bin/time` maximum RSS `1625960 KiB`). Relative to the original
naive twice-run extrapolation this is a `14.04×` end-to-end wall reduction. The
two canonical artifacts are each `93,667,521` bytes and are byte-identical with
SHA-256
`ee6188ba23bcd0b09186d70b8a3231860155783c9e60cfbcd4249158974d711b`.
Each contains all four paths and 1,200 probes/path, trajectory counts `6/6/9/6`,
all polynomial degrees `1/2/3`, and paired report digest
`sha256:56e0127480fc9fd422cc3f1583f7e989eaf347331778630629623a7c3eb521b6`.

The final pytest wrapper exited `1` after the identical artifacts were proven:
its reload assertion compared normalized JSON lists/strings to equivalent
in-memory tuples/enums. Commit `7fa2ffb` fixes that wrapper and its narrow
round-trip regression passes, but the full gate was deliberately not rerun.
Accordingly, scientific artifact parity is proven while the post-fix pytest
exit remains pending one future explicit full-lane execution. Golden artifacts
are never refreshed automatically.

## Merge checkpoints

| Checkpoint | State | Commit(s) | Verification | Independent review |
|---|---|---|---|---|
| C0 contracts/ADR | in review | `67536ba`, `507e0d5`, `5c02938` | plan frozen; canonical scope/plan/science contract tests pass | pending combined review |
| C1 execution foundation | in review | `507e0d5`, `0ac8fb5` | 19 focused pipeline/processing/catalog/migration tests; one Alembic head | independent review active |
| C2 minimal 4-path→2-radio→pair vertical | pending | — | — | — |
| C3 complete receiver science | artifact parity proven; wrapper rerun pending | `5c02938`, `7fa2ffb` | 56 focused tests; frozen one-second equivalence; byte-identical full twice-run artifacts in 11:30.70 | quiet-host distribution and post-fix full-lane exit pending |
| C4 reuse and aggregate science | pending | — | — | — |
| C5 CLI/API/UI surfaces | changes requested | `7107138` | focused Python/web gates passed | independent review found P1 truth/composition issues |
| C6 release candidate | pending | — | — | — |

## Component verification

| Component | Required evidence | State |
|---|---|---|
| Scope/lineage | typed path/radio/paired identities; populated PG migration | implemented; review pending |
| Raw integrity | full compressed/uncompressed verification before run mutation | implemented at expanded-run boundary; review pending |
| One-RX reader | exact RX selection, pinned/no-follow, chunk invariant | pending |
| Quality/power | per-RX continuity/clipping and real time-series power | pure component implemented; production adapter pending |
| Waterfall | frequency X, time Y, full-dwell bounded output | vector-batched full-dwell component implemented and equivalence-tested |
| Probe schedule | exact 1 s / 50 ms / first 20 ms geometry | implemented and tested: 1,200 probes/path |
| Pilot scan | all methods, same-IQ controls, bounded multi-candidate output | implemented; performance optimization active |
| Trajectory bank | linear/quadratic/cubic fits and deterministic families | full raw-IQ artifacts contain all degrees on all four paths |
| Feedback replay | polynomial dechirp, GLRT64 redetection and QAM/control replay | full raw-IQ twice-run artifact parity proven |
| Path report | complete numerical trajectory table and candidate-only status | pure builder implemented; production registration pending |
| Radio reducer | exact RX fan-in, zero IQ reads, partial/truncation algebra | pure reducer implemented; executor vertical pending |
| Paired reducer | exact radio fan-in, shared timing, noncoherent semantics | pure reducer implemented; executor vertical pending |
| Reuse | stable inner artifact, run wrapper, invalidation/concurrency matrix | pending |
| Worker authority | exact release/graph/config match before input access | pending |
| Release/staleness | full-SHA authority, display version, exact stale reasons | pending |
| CLI/API/UI | three rows, RX expansion, aligned plots, TEST evidence visibility | pending |
| Full real E2E | all four paths, two radios, pair, repeat numerical parity | artifacts byte-identical; post-fix pytest wrapper exit pending |
| Performance | bounded four-path CPU/RSS/I/O and frozen benchmark receipt | 14.04× end-to-end wall reduction; quiet-host distribution pending |
| Cutover/rollback | shadow, canary, retention, restart and rollback drill | pending |

## Global commands

These are run only after component gates have passed:

```console
uv run ruff check src tests tools
uv run mypy src
uv run pytest -q
uv run pytest -q -m real_corpus
cd web && npm test
cd web && npm run build
cd web && npm run test:e2e:production
```

Hardware, live PostgreSQL, QNAP and external corpus requirements stay explicit
markers. Required protected local corpus tests fail when their fixture is absent
or has the wrong digest; they do not silently skip or refresh goldens.
