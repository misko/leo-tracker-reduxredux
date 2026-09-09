# Adaptive scanner: actual-visit fractional metrics and resumable backfill

2026-09-09. Adaptive/shadow recordings now have a pure actual-visit fractional
analyzer, pinned read-only IQ adapter, immutable per-visit metrics checkpoints,
bounded resumable service, and an explicit low-priority CLI. **This is an offline
implementation checkpoint, not a deployed scanner or completed analysis UI.**

No radio was contacted, no RF was collected, and no production service was
restarted. No FPGA, kernel, flashed firmware, detector threshold, scientific
fixture or numerical tolerance changed. Remote main was fetched and remains
`29be8492f5f2efb439a9df1e6086224714e95506`, an ancestor of the feature worktree's
parent `f76db32565f514b50e8bdc35c892ca6ef97bb306`. No remote push/merge occurred.

## What now works

The analyzer reads only complete retained visits, in their actual source-time
positions. It does not create a fixed sweep index or treat eight arbitrary
visits as complete channel coverage. Cancelled partial visits are not analyzed
as complete dwells; recorded retune gaps remain gaps.

The existing `analyze_glrt64_dwell` numerical implementation is reused unchanged.
Default offline geometry is 20 ms probes at a 10 ms stride: 11 probes per RX per
120 ms dwell, both receivers analyzed. This is distinct from the **RX1-only
lightweight on-radio detector**. Candidate selection and the margin gate use
complete fractional scores, not integer estimates. Integer diagnostics remain
available for audit. Incomplete refinement and estimates outside the retained
interval remain explicit unavailable candidates, never a signal-absence claim.

Candidate source anchors and relative sample counts serialize as exact uint64
decimal strings. Fractional offsets remain separate. Relative seconds are
computed only after exact integer subtraction; no floating absolute epoch or
phase continuity across retunes is introduced.

Each output binding includes the original public capture-manifest digest, a
validated receipt snapshot, and the full numerical configuration. Different
configurations get distinct content-addressed analysis directories. The source
adapter uses the public IQ reader and its bounded one-chunk cache; the numerical
analyzer imports no storage, radio, HTTP, PostgreSQL or CLI implementation.

## Durability and execution

Each completed visit is a checksummed compressed checkpoint. Writes use exclusive
temporary files, fsync and atomic no-replace publication. Failed temporary files
are retained but never counted as completed work. Existing differing science
cannot be overwritten. Readers reject malformed inventories, changed binding,
corrupt hashes, excess decompression, extra compressed frames/data, symlinks and
hard-linked visit files. All IO is pinned beneath an existing local root; QNAP
roots are rejected.

The final metrics manifest requires every complete source visit exactly once,
with its expected probe count. It records per-visit digests and counts. This is
**metrics completion only**: it does not assert that figures, trajectory joins,
API progress, UI rendering or detector qualification are complete.

The service resumes only missing visits and checks cancellation, visit budget
and time budget between complete visits. A running visit can exceed the time
budget; its numerical windows are not truncated to meet a timer. Exceptions
release reader and worker resources while preserving completed checkpoints.
Receipt validation is retained at ingress and cached for subsequent source-field
comparisons, avoiding a full-receipt parse for every checkpoint.

The new CLI shares the existing desktop analysis lease with fixed V1/V2 workers
and lowers its process priority. The shared lease now has a public no-follow
storage adapter; adaptive backfill no longer needs to instantiate a fixed-product
store merely to coordinate. No new daemon, database, dependency or automatic
scheduler was added. Fixed capture and lightweight-detector defaults are unchanged.

```bash
OPENBLAS_NUM_THREADS=1 leo-adaptive-hop-analysis \
  --bulk-root /absolute/local/recording-root \
  --session-id scan-hop-example \
  --maximum-seconds 300
```

The module entrypoint is also available as
`python -m leo.cli.adaptive_hop_analysis`. The CLI returns an explicit `partial`,
`metrics_complete`, `busy` or nonzero failure result. Rerunning the same binding
resumes it. Default stride remains 10 ms; explicitly requesting a different
stride creates separate products rather than silently weakening dense coverage.

## Saved-IQ numerical and end-to-end verification

The bounded qualification selects the **first saved dwell per rate/edge in
source order**, without consulting scores. These four 120 ms RX1 dwells come
from the already-opened 96-dwell development corpus. This selection covers
CH1 lower/upper at both rates, from two source scans; it is not an all-channel
holdout or an independent sensitivity experiment.

Only RX1 was retained in this corpus export. RX0 is explicitly zero-filled;
adaptive/shadow receipt metadata and UTC brackets are synthetic. Additional
fixture visits needed to exercise upper-target ordering contain synthetic zeros
on both RX. None are published into the real recording root or represented as
observations of unsampled channels.

| Saved case | Candidates checked | Complete fractional candidates | Explicitly unavailable | Integer/fractional selection changes |
| --- | ---: | ---: | ---: | ---: |
| 2.5 MS/s lower | 88 | 61 | 27 | 5 |
| 2.5 MS/s upper | 88 | 54 | 34 | 9 |
| 5 MS/s lower | 88 | 49 | 39 | 6 |
| 5 MS/s upper | 88 | 52 | 36 | 9 |
| Total | **352** | **216** | **136** | **29** |

All retained fractional scores, timing offsets, CFO fields and integer audit
fields match the unchanged direct detector exactly. Selection changes include
abstaining when the integer choice lacks eligible fractional evidence; they are
not 29 new detections or a sensitivity improvement claim. Unavailable outcomes
are checked against the numerical reference rather than silently dropped.

The same four inputs also traverse the real public adaptive IQ codec, a separate
CLI process, read-only source adapter, scientific analyzer, checkpoint store and
sealed metrics reader. All four restored products match the direct products,
apart from the expected new synthetic capture-manifest digest. Twelve CLI
invocations verify completion and idempotence. Each upper fixture stops after
one of five retained visits, then resumes exactly the four missing visits; the
lower fixtures each contain one retained visit. These are **12 synthetic fixture
visits containing four real saved RX1 dwells**, not twelve new RF dwells.

Input/probe hashes are checked against the frozen export. The evidence archive
contains configuration/provenance, numerical outputs, CLI receipts and verified
metrics manifests, but no IQ or executable binaries.

## Runtime finding and limits

Single measured dense-analyzer calls took 3.62–3.92 seconds per tested dwell at
2.5 MS/s and 9.33–9.40 seconds at 5 MS/s. Direct reference calls were comparable.
These desktop smoke timings include a real RX1 and zero RX0, are not repeated
latency-tail measurements, and are **not ARM detector timings or RF duty**.

A naive serial extrapolation to thousands of visits is hours, not a sustainable
20-minute automatic dense-analysis cadence. No multi-hour backfill was launched.
Before automatic dispatch, measure representative full-dual-RX cost and improve
processing capacity/efficiency without silently substituting sparse analysis for
the configured dense product. Bounded resumability makes this work manageable;
it does not itself solve the processing-throughput gap.

## Component verification and retained failures

The final regression run passes **674 tests, zero failed/errors/skipped**. It
covers new analysis/product/storage/service/CLI code, adaptive policy/capture/
history/publication, fixed-scanner compatibility and existing API routes. Ruff,
whitespace checks and mypy on eight source modules pass using Python 3.12.

Four separate full-300-second metadata tests validate both rates and modes,
complete manifest inventory, serialized bounds and missing/reordered-visit
rejection. Their default-plan guards yield 2,290/2,291 complete synthetic visits,
not evidence of real full-length IQ or measured production duty. Short tests
separately exercise genuine synthetic dual-RX IQ storage and restart.

The failure receipts are retained:

- Initial CLI test collection collided with an existing test module basename.
  Renaming the new CLI test fixed collection; no cache deletion or skip was used.
- A new full-span test incorrectly assumed more than 2,400 visits. It now derives
  the exact count from the existing plan's valid dwell, guard and synthetic
  transition samples. No radio timing, fixture or tolerance was changed.
- Existing Starlette/httpx deprecation and pytest `record_property`/xunit2
  warnings remain visible in the final log. They were not suppressed.

The [evidence index](evidence/2026_09_09_adaptive_analysis/index.json) records
commands, environment, source hashes, test receipts and numerical artifacts.
Raw generated data remains under `/tmp/leo-adaptive-analysis.g6WLQT`.

## Remaining work toward the full goal

1. Present the new metrics through bounded actual-visit figure/trajectory products,
   analysis progress and the existing adaptive API/UI. Do not change the current
   UI's `not_integrated` claim until this path is actually connected and tested.
2. Address dense processing throughput before automatic dispatch. Retain explicit
   sampling configuration and shared analysis-resource coordination.
3. Qualify the lightweight detector and scheduling operating point on independent
   saved IQ, then the exact integrated 300-second ARM workload at both rates.
4. Obtain explicit bounded spare-radio RF authorization and verify identity,
   counter-based capture duty, continuity, fallback, restoration and cleanup.
5. Review compatible releases, merge/deploy opt-in, verify a real recording and
   browser analysis path, and exercise rollback.

The [full implementation checklist](../docs/architecture/adaptive-scanner-implementation.md)
remains active. No deployment, live 90% duty, or full-goal completion is claimed.
