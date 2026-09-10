# Fair scanner admission: provider integration and ARM bundle

## Outcome

The [bounded SDK admission prototype](2026_09_10_scanner_fair_sdk_checkpoint.md)
is now connected to the real iiOD metadata provider behind a separate,
default-OFF build option. The fast, deliberately overloaded and sanitized
provider fixtures passed at both 2.5 and 5 MS/s. A new matching ARM userspace
bundle has been cross-built and exercised through the local staging scripts.

This is **not deployed or live-qualified**. No radio was contacted, no RF was
collected, and no firmware, FPGA or production setting changed. The bundle is
not a relabeling of the earlier cooperative-skip bundle: its worker and SDK
both use the new private LP03 pool protocol.

## What changed

`IIOD_SCANNER_GLRT_FAIR_ADMISSION=ON` requires the positive-only SDK, capture
protection and cooperative UNKNOWN skips. Enabling any of those prerequisites
does not implicitly enable fair admission. Incompatible build configurations
fail at configuration time; SDK startup failures remain fatal before capture.

The explicit engineering profile is three occupied slots, 450 ms admission
age, a 500 ms worker watchdog, four recovery blocks, 120 ms maximum pending age
and a 2.5-second freshness trigger. These settings are bound into a new bundle
configuration identity. The provider exposes bounded runtime admission counters
to its component tests, without changing an IIO wire or persisted layout.

The test-only worker wrapper delays the actual numerical entry point by 170 ms,
then runs the original computation. It does not fabricate scores or decisions.
It is linked only into the delayed desktop test worker, never the ARM bundle;
the ARM worker's symbol inventory confirms its absence. Sleep is a controlled
overload stimulus, not a CPU-contention or ARM-performance measurement.

## Provider results

The component fixture drives 20 ms source blocks, with a 20 ms pause between
callbacks, through the real collector, policy, pool, worker and metadata frame
assembly. Only radio operations and IQ are synthetic. RX1 contains pilots on
CH1L, CH3L and CH4L; other targets are zero. RX0 has a sentinel that must remain
unchanged. Each ordinary run spans about four source seconds and 34 visits.

| Build case | Adaptive scenarios | Ordinary-run admission | Result |
| --- | ---: | --- | --- |
| Cooperative, fair option OFF | 14 | Existing admission behavior | Passed |
| Fair, fast numerical worker | 14 | 34 / 34 checks dispatched | Passed |
| Fair, worker delayed by 170 ms | 14 | 22 / 34 checks dispatched | Passed |
| Fair, delayed worker; SDK/provider/policy ASan + UBSan | 14 | 16–22 / 34 checks dispatched | Passed |

The 22 / 34 figure is **64.7% detector dispatch coverage in a short synthetic
test**, not capture duty, RF recall, or a claimed ARM improvement. In the
ordinary unsanitized delayed runs, nine pending requests expired and three were declined
by the freshness guard. All 34 visit records still drained. Intentional skips
did not become NO_SIGNAL claims or fault-fallback choices. The separate
native tests from the preceding checkpoint exercise pending replacement;
these short paced runs did not produce replacements.

The sanitized 2.5 MS/s runs dispatched 19 checks in shadow mode and 16 in
adaptive mode; both sanitized 5 MS/s runs dispatched 22. This timing-sensitive
variation is retained in the evidence, not replaced by the unsanitized counts.
Instrumentation and host scheduling differ between runs, so these receipts
do not isolate its cause or establish repeatable performance percentiles.

Each set of 14 covers both rates, shadow/adaptive operation, cancellation,
genuine failure, owner pressure, recovery and failure after pressure. Healthy
pressure cases resumed real numerical checks and continued weighted scheduling.
Injected genuine faults still latched fixed-order fallback. The fixture also
asserts at most one running and one pending check, no pending/running work at
terminal drain, unchanged RX0 samples, exactly one restore, and complete result
accounting. Both policy fixture binaries passed in all four builds.

The sanitizer run instruments the **SDK, provider and policy**, including the
new HELD ownership path. The isolated numerical worker remains unsanitized;
this is not a claim to sanitize that separate process or prove absence of all
data races. These paced tests also do not bound real capture-owner callback
latency or long-term per-target freshness.

## Transport gate

The 34 CMake configuration tests passed in 24.16 seconds. All **62 localhost
transport tests passed** in 521.35 seconds, with no failures or skips. This
exercises the actual iiOD/parser/TCP/
libiio/PPU/application path, not a physical radio. Full 300-second **source-time**
fixtures use accelerated synthetic IQ, including scheduled recording, durable
readback, cancellation, restoration and HTTP presentation. They do not prove
300 seconds of live RF duty or radio CPU headroom.

The test run emitted 35 existing test-client deprecation and JUnit
`record_property` compatibility warnings; they are not evidence of an RF or
transport failure. The JUnit receipt retains the test cases and their recorded
properties. No test or golden scientific expectation was relaxed.

The report/evidence integrity and preceding admission-model regressions also
passed: 68 cases, including seven new checks of this checkpoint's artifacts.

## New ARM candidate

Sources are Leo `0eb6ee2f8afa6b8b3317f9e9e40221fba553f0bd` and libiio
`b6e692400acd0690767167abc381b0268a640bf7`. The latter is pushed to
`codex/scanner-cooperative-provider`, not promoted to production.

| Identity | SHA-256 |
| --- | --- |
| Bundle manifest | `bc6e5dd53447ce374671eac280b3d9a29abbe40bce6c118bc49546b94d962a25` |
| Algorithm build | `2f9eb3b754ae241f78d4d58a6269e3c8fe0bda681ab2e60a32f7677bafc8f2bd` |
| Runtime configuration | `2af4982425b543279b1c6be6ba251cd6a4ce05826be17f5dafc976bb4190be12` |

Nine payloads total 3,477,064 bytes: daemon, SDK, matching numerical worker,
four shared-library dependencies and two template files. ELF checks verified
ARM hard-float headers, the expected library dependency closure, and a dedicated
runtime search path. The release remains local. Twelve local shell operations
staged, verified and cleaned up the eight companion files with matching hashes;
the shell runner made zero remote calls and did not execute any ARM payload.
Only test-owned scratch was removed; the original release was retained.

## Remaining gates before promotion

1. Compare actual SDK admission and service timing with the independent model
   over longer, jittered and uneven target schedules. The model's instantaneous
   completion servicing differs from real owner polling; a 2.5-second trigger
   is not a guaranteed maximum revisit interval.
2. Measure saved-IQ ARM execution, owner copy/service costs, memory use and
   startup/library compatibility on an allowed, available radio without RF.
   The current cross-build cannot establish these properties.
3. With explicit authorization, qualify the candidate in a bounded live run:
   verify 300-second capture duty/continuity, detector coverage by target,
   activity/cooldown behavior, overload recovery, restoration and published
   analysis/UI products. Do not convert skipped computation into silence.
4. Promote the exact qualified userspace bundle, merge the relevant sources,
   deploy and verify the production schedule. Do not reuse an earlier identity
   or claim the existing 2.5 MS/s runtime qualifies this new fair policy.

The [evidence index](evidence/2026_09_10_scanner_fair_provider/index.json) binds
original logs, build commands, source snapshots, sanitizer scope, bundle
receipts and component summaries. It contains no IQ, executable, credential
or key. The preceding [admission model report](2026_09_10_scanner_provider_admission.md)
remains a counterfactual study, not a measurement from the new ARM candidate.
