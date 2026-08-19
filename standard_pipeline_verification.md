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

Observed on 2026-08-19: the science call took `20.205403713 s`; the complete
pytest command, including full fixture digest verification, took `24.13 s` and
peaked at `358988 KiB` RSS. It processed one real RX path for one coarse second,
including 20 probes with at most four scored candidates per probe.

The deliberately simple `20.205403713 × 60 × 4 × 2` extrapolation is
`9698.59378224 s` (about 2 h 41 m 39 s). It is diagnostic, not a runtime
promise, but it proves the full twice-run regression is not yet lean enough.
The full four-path/two-radio/pair twice-run test is defined in
`tests/analysis/test_standard_real_corpus_e2e.py`, uses two separate temporary
output roots, and compares scientific JSON field-by-field using the frozen
tolerances in `corpus/goldens/trial-132-standard-v2-summary.json`. It was not
run and must remain **pending** until component optimization makes it practical;
goldens are never refreshed automatically.

## Merge checkpoints

| Checkpoint | State | Commit(s) | Verification | Independent review |
|---|---|---|---|---|
| C0 contracts/ADR | in progress | — | — | — |
| C1 execution foundation | in progress | — | — | — |
| C2 minimal 4-path→2-radio→pair vertical | pending | — | — | — |
| C3 complete receiver science | pending | — | — | — |
| C4 reuse and aggregate science | pending | — | — | — |
| C5 CLI/API/UI surfaces | pending | — | — | — |
| C6 release candidate | pending | — | — | — |

## Component verification

| Component | Required evidence | State |
|---|---|---|
| Scope/lineage | typed path/radio/paired identities; populated PG migration | pending |
| Raw integrity | full compressed/uncompressed verification before run mutation | pending |
| One-RX reader | exact RX selection, pinned/no-follow, chunk invariant | pending |
| Quality/power | per-RX continuity/clipping and real time-series power | pending |
| Waterfall | frequency X, time Y, full-dwell bounded output | pending |
| Probe schedule | exact 1 s / 50 ms / first 20 ms geometry | pending |
| Pilot scan | all methods, same-IQ controls, bounded multi-candidate output | pending |
| Trajectory bank | linear/quadratic/cubic fits and deterministic families | pending |
| Feedback replay | polynomial dechirp, GLRT64 redetection and QAM/control replay | pending |
| Path report | complete numerical trajectory table and candidate-only status | pending |
| Radio reducer | exact RX fan-in, zero IQ reads, partial/truncation algebra | pending |
| Paired reducer | exact radio fan-in, shared timing, noncoherent semantics | pending |
| Reuse | stable inner artifact, run wrapper, invalidation/concurrency matrix | pending |
| Worker authority | exact release/graph/config match before input access | pending |
| Release/staleness | full-SHA authority, display version, exact stale reasons | pending |
| CLI/API/UI | three rows, RX expansion, aligned plots, TEST evidence visibility | pending |
| Full real E2E | all four paths, two radios, pair, repeat numerical parity | pending |
| Performance | bounded four-path CPU/RSS/I/O and frozen benchmark receipt | pending |
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
