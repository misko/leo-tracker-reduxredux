# Adaptive scanner: application contracts and durable actual-visit recording

2026-09-09. **The application recording foundation now preserves adaptive visits
and source-time decisions, including complete synthetic 300-second TCP captures.
Scheduled adaptive operation, its UI, and deployment are not complete.**

No RF, radio connection, production-service change, firmware flash, FPGA or
kernel change belongs to this checkpoint. All network tests connect only to
127.0.0.1; their nominal 192.168.1.14 client identity is a substituted fixture,
not an accessed radio.

## Implementation

- New application-owned adaptive plan/event/visit/terminal/receipt contracts
  use new schema-V1 kinds. The wire identity remains explicit major V2. Neither
  the fixed-order capture contracts nor the existing fixed-IQ manifest V2 is
  repurposed. Both receivers remain recorded; policy/classification is RX1-only.
- Decisions retain actual targets separately from shadow proposals, the source
  basis visit, integer sample-counter decision time, active/quiet masks, selected
  proposal's miss count, cooldown and reason. No synthetic sweep coordinate is
  assigned. The pinned three-miss AND two-second policy is unchanged.
- The application validates actual source sequence, tuning, guards, complete
  dwell intervals, terminal inventory and restoration. It retains every event
  on cancellation but never counts an unfinished final dwell as complete IQ.
  Counters above 2**53 stay integers. Existing separate GLRT fractional offsets
  are untouched; this is not a new Doppler estimator.
- An explicit PPU V2 mapping boundary compares the armed request with the
  application plan, checks radio identity and exact host cleanup, and verifies
  actual visits and per-target coverage. Detector-reporting failure remains
  advisory; it cannot turn bad IQ evidence into a successful recording.
- The independent `scanner-adaptive-recordings` store writes lossless CI16 into
  independently compressed blocks of up to eight chronological visits. These
  are storage chunks, **not eight-channel sweeps**. It retains actual visits,
  source accounting, clock uncertainty and queue telemetry in a sealed manifest.
- Directory descriptors pin a pre-created local root and reject symlinked
  traversal/QNAP targets. A session directory is reserved exclusively; existing
  or incomplete sessions cannot be overwritten. Atomic Linux `renameat2` with
  NOREPLACE publishes the manifest after compressed data is finalized and synced.
  Failed staging data is retained. Readers enforce bounded regular single-link
  files, manifest/chunk/session hashes, decompression limits and no trailing frames.
- A bounded compression worker uses nonblocking enqueue. Exhaustion is an
  explicit capture failure, never an IQ drop presented as success. Cancellation
  or a timed-out worker cannot close a file still owned by that worker.
- Capture orchestration records valid visits through narrow ports, checks the
  terminal receipt against delivered IQ, prefers the precise device-open clock
  bracket, closes the radio and applies an external safety barrier before
  publication. It preserves primary failures and cleanup diagnostics.

## Verification scope

The [final evidence index](evidence/2026_09_09_adaptive_recording/final/index.json)
records the final test receipts, source hashes, native fixture identity, style
and type checks. Earlier attempts remain in the same evidence tree, including
the initially green run whose empty-capture accounting was subsequently found
incorrect by inspecting its per-case properties.

| Lane | Final checks | Scope |
| --- | ---: | --- |
| Leo portable | 509 | New contracts/application/storage/queue plus fixed scanner, radio, policy, publication, CLI and history/API regressions |
| PPU portable | 1,043 | Adaptive/fixed capture, early cancellation and latest-main pilot/PSS/fine-ledger regression suites; fake hardware only |
| Actual adaptive TCP | 34 | Twelve application-mapping/store cases plus 22 previous transport/client/fault cases |
| Static validation | Passed | Ruff, strict project typing on Python 3.12, whitespace checks; no dependency-pin changes |

The twelve new TCP cases cover both rates and both modes, each with complete
capture, cancellation after 30 delivered visits and cancellation before the
first refill. The four complete cases each persist and verify **2,480 visits**:

| Rate | Source span (samples) | Valid dual-RX IQ verified, per mode |
| --- | ---: | ---: |
| 2.5 MS/s | 750,209,920 | 5,952,000,000 bytes |
| 5 MS/s | 1,500,409,920 | 11,904,000,000 bytes |

These source spans are slightly over 300 seconds because the final valid dwell
is completed. The TCP fixture uses synthetic constant RX0 and zero RX1, an
accelerated clock and an explicit **1 ms test guard**. It does not change the
production guard, establish useful-signal sensitivity, measure ARM load, prove
live duty or demonstrate a positive-signal scheduling improvement. Storage tests
separately exercise non-fixed target orders after the startup warmup.

The fixture radio/application orchestration tests and the actual TCP-to-mapper/
store tests are separate lanes. A production adaptive radio-session adapter and
scheduled composition are still required; the current fixed production adapter
has not silently been converted into one.

## Issues found and corrected

1. **Serialization boundary:** an initial implementation passed a Pydantic
   model directly to the JSON-compatible canonical encoder. The combined first
   run had 18 failures/56 passes. Explicit JSON-mode model projection fixes the
   implementation; no validation or scientific tolerance was relaxed.
2. **Decompression bounds:** the next run had four full-chunk failures/70
   passes because the selected decoder's window-size limit was configured too
   small. The reader now enforces an explicit byte bound on the frame header and
   decoder, checks declared content size before allocation, limits unknown-size
   expansion and rejects trailing data. The bounded store tests then passed.
3. **Repeated long-manifest work:** readback originally reparsed and validated
   the full 2,480-visit manifest for each of 310 chunks. A local measurement found
   roughly 101 ms for inspection and 111 ms for one chunk call. A pinned reader
   now validates once and caches one chunk; the corresponding spot measurement
   was 129 ms to open, 14 ms for an uncached chunk and 20 microseconds for a cached
   visit. These are desktop observations under test load, not ARM estimates or
   stable performance guarantees. Tests assert bounded caching and checksum checks.
4. **Test-server lifetime:** both 5 MS/s complete captures initially finished
   storage verification but failed fixture teardown with SIGALRM. The server's
   unchanged 90-second watchdog had included unnecessary offline readback time.
   The test now closes the server before reopening the recording read-only.
   No hardware timing gate or watchdog was extended. The failed run's 28 passes
   and two failures are retained.
5. **Cancellation before first IQ:** the real TCP test exposed an unnecessary
   refill of an already-cancelled acquisition, returning EINVAL. PPU now goes
   directly to terminal status and result drain when cancellation precedes
   iteration. Owned tests require that no IQ read occurs and restoration remains
   exact. This is an adaptive client correction, not a wire/FW change.
6. **Unset source origin:** reviewing the first green empty-cancel receipts
   revealed an apparent duration near 2**53 samples: raw HOPT had an unset zero
   first counter and an absolute final device counter. A new explicit
   `source_span_attested` flag prevents treating that subtraction as elapsed
   capture time. Without an actual startup event, elapsed/duty totals are
   unavailable (zero-valued counters with this flag false), not a measured
   zero-duration scan; consumers must display N/A. Raw terminal evidence is
   retained. Both domain and real TCP tests now assert this distinction.

An earlier corruption test also accidentally assigned an unchanged duty flag;
that fixture was corrected. Failed attempts are preserved. The existing
Starlette/httpx deprecation warning remains visible. Type checks used the actual
Python-3.12 environment; no fresh Python-3.11 compatibility pass is claimed.

## Source and release state

Dedicated worktrees were preserved. Freshly fetched Leo main at `29be8492` is
already an ancestor. PPU's independent finite-pilot progress and raw-PSS batch
updates at `ffc4113`/`a0b4918` were merged conflict-free into the feature branch
at `1845d01`. The subsequently published independent fine-schedule ledger at
`90eaecd` was also merged conflict-free at `2799f2c`; its owned tests are included.
Early-cancellation handling is committed at PPU `c574eb3`, and unattested-origin
accounting at `ba9adf9`. Exact final implementation hashes and revisions are
retained in the evidence index. The native fixture reuses libiio
checkpoint `42762db3`; no libiio code was changed in this work.

Nothing was pushed, merged into remote main or deployed. The full
[execution checklist](../docs/architecture/adaptive-scanner-implementation.md)
remains active:

1. Add the concrete adaptive radio-session adapter and scheduled runtime
   composition, preserving ownership/admission/alternate-iiOD cleanup barriers.
2. Bind advisory classifier publication to actual adaptive events, add history/
   API/UI activity and allocation views, and route Doppler analysis through
   actual visit times. Empty/unattested source spans must not become chart axes.
3. Qualify frozen detector quality on held-out saved IQ and the exact integrated
   build under paced 300-second ARM load at both rates. Older worker measurements
   and these accelerated TCP cases do not satisfy those gates.
4. Obtain explicit bounded RF-canary authorization, preserve excluded devices
   and production ownership, then compare source-counter duty and reacquisition.
5. Review compatible releases, merge the required remote branches, deploy opt-in,
   verify recordings/UI/cleanup and exercise rollback before declaring completion.
