# Fair scanner admission: native SDK checkpoint

## Outcome and boundary

The bounded admission prototype is now implemented in the actual SDK/shared
pool, behind a new explicit startup-only opt-in. It uses the existing three
preallocated IQ buffers: one running check, one complete pending dwell, and one
partially collected dwell. No extra IQ allocation, numerical algorithm change,
firmware change, radio access or production deployment occurred in this step.

**1,270 native regression cases passed**, including 134 new held-pool and
fair-admission cases. A further **42 science/recovery cases passed**, comparing
the opt-in worker's fractional GLRT/CFO output with the direct numerical oracle
and testing recovery after aborting the third, partially filled slot. The
previous admission-model/evidence checks also remain green (61 tests).

This remains on `codex/scanner-5m-cooperative-skips`, not main or the production
radio runtime. The [modeled improvements](2026_09_10_scanner_provider_admission.md)
are still not measured gains from this SDK. The previously built cooperative
bundle does **not** include this fair-admission implementation and must not be
relabeled or reused as if it did.

## Implementation

`leo_scanner_glrt_enable_fair_admission()` requires positive-only operation,
cooperative UNKNOWN skips, capture protection, and three available pool slots.
The tested configuration is 120 ms maximum pending age and a 2.5-second
freshness trigger, with existing protection set to three occupied slots,
450 ms admission-age threshold, 500 ms watchdog and four recovery blocks.
Neither linking the new SDK nor enabling the earlier cooperative option turns
fair admission on. Existing callers keep FIFO behavior.

A complete pending dwell remains in a private HELD state, invisible to the
worker until publication. Only the acquisition owner can replace or release
HELD storage. Exact request identity prevents a stale slot reference from
releasing a reused slot. READY and WORKING storage cannot be revoked. There is
at most one published/running request and one selected pending request; a just
completed third buffer is resolved synchronously before returning to capture.

On overload, selection prefers the least recently dispatched target. The
freshness guard can intentionally decline a fresh target while a previously
observed target is overdue. It is pressure-qualified and expires after a quiet
interval, so a fast worker continues checking every dwell. This uses dispatch
history, **not** positive-detection history, and never changes cooldown or
activity timestamps. The freshness trigger is not a hard maximum-age guarantee.

Pending age is checked against both CLOCK_MONOTONIC and the latest observed
source counter. The equality boundary is allowed; work older than the configured
limit is discarded. Worker timeout still applies independently to submitted
work. Checks run only when the owner calls the SDK; there is no new timer,
thread, allocation, blocking wait, IIO operation or receive-buffer ownership.

An intentional replacement, expiry or freshness skip remains unavailable with
zero search coverage and healthy UNKNOWN feedback. Pressure shedding remains
distinct from cancellation and genuine worker/clock failures. Public wire
records and scheduler observations still drain in original visit order.
Normal terminal drain keeps the worker notification pipe open until held work
is dispatched or discarded; cancellation discards unsubmitted held work with
the existing cancellation semantics. A real fault cannot be cleared by skips.

## Compatibility and tests

The private same-build pool magic advances from LP02 to LP03. This is necessary:
an older FIFO worker must not silently consume a HELD-capable mapping under
incompatible ownership rules. Public request/result/hop layouts and existing
SDK configuration structures are unchanged.

The actual archived old numerical worker (SHA-256
`2191e8ed881bf7a01769bbb0288ac41a0c21664aced57a1a2fdd582e6ee859c0`)
was tried with the new desktop SDK. Open failed with EIO before returning a
session, and the child was reaped. No device or daemon was involved. The unit
test for the opposite mapping direction models the old magic inventory; it is
not a claim to execute a historical SDK binary.

| Check | Result |
| --- | --- |
| New pool/SDK cases | 134 passed; included in the 1,270 |
| Full selected native SDK/pool/worker/policy/frame regression | 1,270 passed in 126.19 s |
| Additional fractional-oracle and partial-pressure recovery cases | 42 passed in 18.45 s |
| Existing admission model and hash-indexed report reproduction | 61 passed |
| Cortex-A9/NEON/hard-float SDK cross-build | Passed, warnings treated as errors |
| Actual old worker + new SDK startup | Rejected with EIO, no returned session, child reaped |
| Changed Python lint and whitespace | Passed |

Native tests cover both sample rates and seven numerical worker build variants.
They exercise three-slot occupancy, visibility, exact identity/reuse, complete
terminal inventories, pending replacement, both expiry clocks, cancellation,
pressure suspension/recovery, true watchdog failure, and an overdue-target
freshness sequence. The latter includes an explicitly synthetic source-time
gap; it does not claim physically paced live-stream timing. Source counters
above 2^53 and fractional offsets remain separately preserved. The oracle
comparison checks fractional offset, CFO, exact/control scores and margin at
the existing relative 1e-9 / absolute 1e-10 tolerances. Caller RX0/RX1 bytes
remain unchanged. No golden fixture changed.

## Remaining qualification work

Follow-up: the [provider integration and ARM bundle checkpoint](2026_09_10_scanner_fair_provider.md)
adds explicit provider activation, paced overload/sanitizer tests and a matching
local userspace bundle. The list below records the open gates at this SDK
checkpoint; the follow-up distinguishes completed integration from remaining
ARM execution and live qualification.

1. Add default-OFF provider activation, a newly identified full userspace
   bundle containing the matching worker, and real provider replay tests for
   the fair policy. The older provider/bundle receipts qualify only cooperative
   skips, not this additional opt-in.
2. Compare actual SDK admission against the independent model over delayed,
   jittered, uneven and overloaded schedules. Owner polling adds dispatch
   latency; the model assumed immediate completion servicing. The old age
   guard also still applies, so matching policy settings must be explicit.
3. Run new sanitizer/concurrency checks for the HELD ownership path. Earlier
   provider ASan/UBSan evidence predates this implementation and is not claimed
   to cover it.
4. Measure saved-IQ ARM timing and capture-owner copy/service costs on an
   allowed available radio, without opening RF. Confirm genuine detector
   decisions and distinguish coverage from result age.
5. Only after these checks, separately authorize a bounded live qualification,
   verify duty/continuity/coverage/restoration/UI, and promote/deploy the
   qualified candidate. Production remains on its earlier verified runtime.

The [evidence index](evidence/2026_09_10_scanner_fair_sdk_checkpoint/index.json)
binds source files, tests, JUnit receipts, ARM build provenance and old-worker
rejection evidence. It contains no IQ, binary, credential or private key.
