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
| Read-only QNAP archive | `/mnt/qnap01/mouse9911/leo-store/test-corpus/trial-132-four-path-v1` |
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

### QNAP archive receipt

On 2026-08-19 the requested redundant archive was copied from the already
verified local fixture as an explicit operator action. The destination did not
previously exist; no QNAP file was deleted or replaced. All destination files
were sealed mode `0444` and directories mode `0555`, then verified read-only
through `RecordingStore`.

Observed destination receipt:

```text
manifest_sha256 sha256:1712bf9293b684540824ad4adfe0764a3477d01d7da8fdb28398ae465076855d
VerificationReport(session_id='production-24h-20260819-01-trial-00000132',
  chunk_count=18, compressed_bytes=1179238949,
  uncompressed_bytes=2400000000, timeline_count=2)
```

The procedure was:

```console
src=/srv/bulk/leo/test-corpus/trial-132-four-path-v1
dst=/mnt/qnap01/mouse9911/leo-store/test-corpus/trial-132-four-path-v1
mkdir -p -- "$dst"
rsync -a --checksum -- "$src/" "$dst/"
find "$dst" -type f -exec chmod 0444 -- {} +
find "$dst" -type d -exec chmod 0555 -- {} +
uv run python -c 'from pathlib import Path; from leo.storage import RecordingStore; s=RecordingStore.open_read_only(Path("/mnt/qnap01/mouse9911/leo-store/test-corpus/trial-132-four-path-v1")); print(s.verify(s.inspect("production-24h-20260819-01-trial-00000132"))); s.close()'
```

This remains an operator-only archive action. Repository code and automated
tests use the protected local fixture and do not create, delete, move, rename,
chmod, or require anything beneath `/mnt/qnap01`.

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

The current complete one-second output is frozen at
`corpus/goldens/trial-132-standard-v2-one-second-frozen.json`, SHA-256
`e26bc5b5fc8c5573713e9e8f730361f1081e9720baecdbfe24c9af68feaf47b9`.
Every one of its 9,739 floating fields is compared to optimized output at the
reviewed absolute/relative tolerances; shape and non-derived fields remain
exact. The latest bounded stream-0/RX0 science call was `4.999633068 s` for one
second and 20 probes; that timing is an interference receipt, not a quiet-host
release distribution.

The corrected complete four-path/two-radio/pair analysis was executed twice
from raw IQ in isolated processes and create-only output roots. Independent
review froze the complete per-path scalar and trajectory-model inventory in
`corpus/goldens/trial-132-standard-v2-summary.json` (SHA-256
`0b13a4c0b09cda17fc971e66396b5673c6b89eb8cef9fcef3ddcf8bc87309daa`).
The two canonical artifacts were each `93,713,940` bytes and byte-identical,
SHA-256
`cae4c4e44f72749211ccd65a3f0af776adfb82031eb0250cdedaf15fb93a9886`.
They contain all four paths, 1,200 probes/path, trajectory counts `6/6/9/6`,
every polynomial degree `1/2/3`, and paired report digest
`sha256:d99fb15e980920240b320a76ec5e59ec759b59cdc26ee0c1e51e2880f2b43f5d`.

After review and freeze, the exact full gate was rerun cleanly:

```console
uv run pytest -q -m real_corpus tests/analysis/test_standard_real_corpus_e2e.py::test_trial132_full_four_path_twice_is_numerically_identical --basetemp=/srv/bulk/leo/test-output/standard-v2-corrected-review-d
```

Observed: `1 passed in 687.16s (0:11:27)`. Both newly created artifacts again
had the exact byte count and SHA-256 above. The independently reviewed receipt
is `corpus/goldens/trial-132-standard-v2-full-review-receipt.json`; its SHA-256
is `c7e354b9edd4989673cdc860d9ea61610f4d96bccdb6163e35ac5977150d1105`.
The non-real gate hard-pins and cross-checks both golden and receipt hashes;
tests have no refresh path.

## Merge checkpoints

| Checkpoint | State | Commit(s) | Verification | Independent review |
|---|---|---|---|---|
| C0 contracts/ADR | contract slices passed | `67536ba`, `507e0d5`, `5c02938`, `bf2e651` | plan and canonical scope/plan/science/station contracts frozen | each corrected slice independently passed; combined production vertical still required |
| C1 execution foundation | complete | `507e0d5`, `0ac8fb5`, `795335f`, `5e181a0`, `b2319fc` | 134 author tests; 60+9 independent PG/adversarial tests; Ruff/mypy; one Alembic head `a85e4c71d9f0` | PASS, no P0/P1 |
| C2 minimal 4-path→2-radio→pair vertical | pending | — | — | — |
| C3 complete receiver science | pure science and corpus gate passed; production analyzer wiring pending | `5c02938`, `6c8bdc3`, `7fa2ffb`, `b79203e`, `7df2c27` | 134 non-real science tests; independently reviewed frozen golden; clean full twice-run in 687.16s | PASS on science contracts/golden; C2 production execution remains prerequisite |
| C4 reuse and aggregate science | pending | — | — | — |
| C5 CLI/API/UI surfaces | bounded recording surfaces passed; Standard-v2 production binding pending | `7107138`, `402f142`, `55121b8`, `79d3eaf`, `161ffd6`, `fd5fc7d` | 69 focused Python; 10 Vitest; Vite build; production Playwright 2/2 | contract/read-only layer passed; authoritative Standard-v2 adapter still required |
| C6 release candidate | pending | — | — | — |

## Component verification

| Component | Required evidence | State |
|---|---|---|
| Scope/lineage | typed path/radio/paired identities; populated PG migration | contracts and immutable run snapshots passed; station→catalog integration pending |
| Raw integrity | full compressed/uncompressed verification before run mutation | passed at the service boundary, including no-follow and forged-attestation tests |
| One-RX reader | exact RX selection, pinned/no-follow, chunk invariant | independently passed, including 300-chunk FD bound and root/child swaps |
| Quality/power | per-RX continuity/clipping and real time-series power | pure component implemented; production adapter pending |
| Waterfall | frequency X, time Y, full-dwell bounded output | vector-batched full-dwell component implemented and equivalence-tested |
| Probe schedule | exact 1 s / 50 ms / first 20 ms geometry | implemented and tested: 1,200 probes/path |
| Pilot scan | all methods, same-IQ controls, bounded multi-candidate output | optimized, frozen-equivalence tested and independently reviewed |
| Trajectory bank | linear/quadratic/cubic fits and deterministic families | full raw-IQ artifacts contain all degrees on all four paths |
| Feedback replay | polynomial dechirp, GLRT64 redetection and QAM/control replay | full raw-IQ twice-run artifact parity proven |
| Path report | complete numerical trajectory table and candidate-only status | pure builder implemented; production registration pending |
| Radio reducer | exact RX fan-in, zero IQ reads, partial/truncation algebra | pure reducer implemented; executor vertical pending |
| Paired reducer | exact radio fan-in, shared timing, noncoherent semantics | pure reducer implemented; executor vertical pending |
| Reuse | stable inner artifact, run wrapper, invalidation/concurrency matrix | pending |
| Worker authority | exact release/graph/config match before input access | independently passed with attempt-neutral mismatch and live revalidation fences |
| Release/staleness | full-SHA authority, display version, exact stale reasons | pending |
| CLI/API/UI | three rows, RX expansion, aligned plots, TEST evidence visibility | bounded recording list/stage matrix and production browser gate pass; Standard-v2 authoritative adapter pending |
| Full real E2E | all four paths, two radios, pair, repeat numerical parity | clean component-level full gate: 1 passed in 687.16s; typed PostgreSQL production vertical pending |
| Performance | bounded four-path CPU/RSS/I/O and frozen benchmark receipt | full twice-run is 11:27 under contended host; five-run distribution/resource enforcement pending |
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
