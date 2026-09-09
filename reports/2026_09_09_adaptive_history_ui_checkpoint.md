# Adaptive scanner history, API and operator UI

2026-09-09. Adaptive and shadow recordings now have a separate read-only history,
actual-visit detail view and source-bound radio GLRT endpoint, wired into the
existing production API composition and scanner React UI. This is a local
implementation checkpoint, **not deployment or detector/ARM/RF qualification**.

No radio connection, RF collection, production restart, firmware flash, kernel
change, FPGA change, remote push or merge was performed in this checkpoint.
The existing local React/Python service architecture and dependencies remain.

## Operator-facing behavior

- The scanner browser lists adaptive/shadow captures separately from fixed-order
  sessions. A selection shows actual target visits over device time, allocation,
  revisit and unobserved intervals, and a paginated decision inventory.
- Actual and proposed targets are distinct, particularly in shadow mode. The
  selected decision shows all eight activity states, its source-feedback basis,
  reason, and the **proposed target's** miss count and cooldown. Scheduling state
  is not labelled as a per-dwell detection verdict or a calibrated probability.
- Every started hop is retained in the metadata inventory. Only complete visits
  count as retained IQ. An incomplete-hop marker uses its invalid-interval start,
  because cancellation during a guard can precede the valid sample boundary.
- Capture qualification, detector evidence and dense analysis readiness remain
  independent. The GLRT panel reads separately bound adaptive evidence; missing
  or failed evidence does not become signal absence or hide a recording.
- Dense GLRT/CFO trajectory analysis is explicitly **not integrated**, not queued
  or complete. No fixed-sweep worker is invoked and no synthetic sweep index is
  introduced. Actual-time analysis integration is still required.

## Contracts and numerical definitions

New application read-model kinds and `/api/v1/scanner/adaptive-sessions` routes
are additive. Existing fixed-history, fixed-analysis and GLRT publication versions
are unchanged. Detail and GLRT routes validate identifiers and source binding;
missing support/data returns 404, invalid evidence returns sanitized 409, and
HEAD has no response body. These routes do not trigger capture or analysis.

Source origins, valid boundaries, decision counters and policy generations are
serialized as canonical uint64 decimal strings. Relative plot time is computed
after exact integer subtraction. The browser verifies the source/time relation
and rejects rounded numeric epochs. Existing fractional GLRT offsets remain
separate from their integer anchors.

| Measurement | Definition |
| --- | --- |
| Capture duty | Receipt's complete retained sample count / attested device-counter capture span |
| Allocation | A target's complete retained valid time / all targets' complete retained valid time |
| Maximum revisit | Largest start-to-start interval between that target's complete retained visits; unavailable with fewer than two |
| Maximum unobserved interval | Longest interval without complete retained target IQ, including capture-start and capture-end boundaries |
| RF UTC | Existing host-bracketed first-sample estimate, with qualification and bracket width shown separately |

Empty pre-refill cancellation has no attested source origin, span, RF UTC or
duty: these are nullable/unavailable, never invented zero measurements. Recording
creation time is labelled as a fallback, not misrepresented as RF start. A target
with no retained visits but an attested capture has an unobserved interval equal
to the full capture span. No interval is extrapolated beyond the recording.

Storage presentation uses public manifests and never decompresses IQ. A public
single-pass manifest iterator preserves strict corruption handling and lets
history retain only ordering keys rather than every full scan manifest. Per-page
summaries are computed for the selected captures. Listing still validates the
published manifests; large-history latency needs measurement before adding an
index/cache. No database or new service was introduced for this path.

## Verification

The [evidence index](evidence/2026_09_09_adaptive_history/index.json) records source
hashes, commands and compressed final receipts. Raw generated output remains in
`/tmp/leo-adaptive-history.EkWZKs`.

| Lane | Final result | Scope |
| --- | --- | --- |
| Python | 496 passed, 0 skipped | New read models/storage/API plus adaptive and fixed capture/publication/schedule regressions |
| Frontend | 121 passed, 0 skipped | React/DOM and response-boundary tests, including scanner selection and fixed-view compatibility |
| Web production build | Passed | TypeScript plus Vite; no dependency or lockfile changes |
| Static | Passed | Ruff, whitespace, three source modules checked with Python-3.12 mypy target |

The API's four synthetic full-300-second metadata cases cover both rates and
both modes. Each exposes 2,480 actual visits with exact source inventory and
approximately 1.053 MB of JSON. Single measured projection/ASGI times were
0.112–0.145 seconds. These are desktop metadata-only timings, **not** disk-history
scaling, browser rendering benchmarks, ARM throughput, RF duty or detector quality.
The full-span fixtures substitute metadata manifests and do not claim IQ exists.

Separate short tests write actual synthetic dual-RX IQ through the existing
adaptive store, then verify read-only history without invoking any IQ decoder.
The actual production composition serves an initially empty history, discovers
newly published IQ and GLRT evidence without restarting, and serves both while
a test hook forbids opening any PostgreSQL connection. No live database is used.

Tests cover cancelled tails and guard cancellation, empty captures, unavailable
metrics, actual/proposed target differences, all eight coverage rows, corrupt
manifests, wrong manifest binding, precise epochs above 2**53, fractional offsets,
pagination, unsupported old servers, stale/late response rejection, nonoverlapping
polls, loading/errors and selection between adaptive and fixed recordings.

This checkpoint has no real-browser screenshot or deployed browser verification.
The existing JSDOM canvas/WebGL warnings, Starlette/httpx deprecation and Vite
large-chunk warning remain visible in receipts. Initial test harness fixes added
the pre-existing production `recordings` directory to its fixture and removed an
unsupported Testing Library type option. Neither required production validation
or numerical thresholds to be relaxed.

## Remaining release work

1. Connect bounded dense analysis to actual adaptive visits and fractional source
   times; retain old/new analysis compatibility and truthful UI progress.
2. Freeze and qualify detector/scheduling quality on independent saved-IQ holdout.
   Current positive-only scheduling hints are not validated absence claims.
3. Qualify the exact integrated 300-second ARM workload at both rates, including
   original block arrival, startup tails, CPU, memory and bounded backlog. Older
   5 MS/s worker CPU p99 exceeded the 100 ms target.
4. Separately authorize bounded spare-radio RF canaries; attest permitted serial
   and LAN identity, unchanged duty/continuity and final cleanup.
5. Review compatible remote revisions, merge/release, opt-in deploy, verify the
   recording/UI path on the deployed service, and exercise rollback.

The [full implementation checklist](../docs/architecture/adaptive-scanner-implementation.md)
remains active. Fixed scanning remains the default.
