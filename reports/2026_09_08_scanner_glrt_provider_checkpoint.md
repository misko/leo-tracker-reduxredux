# Scanner GLRT: acquisition port and actual SPF provider integration

2026-09-08. **Implemented and tested offline; not deployed or qualified for
unchanged live scanner duty.** No radio was accessed during this checkpoint.
No RF, production service, FPGA, kernel, or flashed-firmware change occurred.

## Outcome

The actual SPF frame provider now has an opt-in path from counter-attested
120 ms RX1 dwell samples through the isolated numerical worker to LGC1 frame
metadata and its same-session terminal drain. Dual-RX recording is retained.
This closes a real provider integration gap; it does not yet connect the
production host capture session or qualify the classifier's decisions.

Source commits:

- Leo `73141b0f5279733a7baf755660639a1bba087bde`: bounded acquisition SDK,
  LGO1 C/Python request contract, component tests and build receipts.
- libiio `af12ce68f8bb3f101c38f0332efe157513367a27`: actual SPF provider/bridge,
  opt-in build/capabilities, exact-gap handling and provider-owned tests.

Both are local implementation-branch commits. Neither was pushed, merged into
remote main, installed, or deployed in this checkpoint. The unrelated default
workspace was left untouched.

## Implementation

The narrow public `scanner_glrt.h` API keeps private numerical and shared-memory
structures out of iiOD. A startup-only allocator creates bounded RX1 history,
three worker slots, and an ordered result ledger. History recovers dwells whose
hop events arrive after the corresponding samples; expired history and counter
gaps become unavailable input. The worker never retains a DMA buffer.

Worker/template paths are operator-configured, not client input. Regular-file,
ownership, write-permission and final-symlink checks precede descriptor-pinned
execution. Unrelated descriptors are closed before exec using close-range
where available or the older kernel's descriptor-limit fallback. The existing
worker privilege/resource restrictions remain. Missing artifacts fail startup,
and processing failures remain separate from recording policy.

LGO1 wraps the unchanged tandem/HOPR request with a versioned 96-byte header,
generation, fixed selected RX and algorithm/configuration identities. It is
bounded to the existing 4096-byte request limit. The provider admits the exact
current scanner geometry: 120 ms visits, 2.5/5 MS/s and matching bandwidth,
dual-RX capture, the documented eight-profile channel/edge order, and at most
a 300-second envelope. Generic burst/ring requests do not silently opt in.

Accepted IQ frames carry unchanged V6/HOPS metadata inside LGC1, with at most
four ordered completed results. Original uint64 counters and separate
fractional offsets are retained; later carrier-frame time is never substituted
for source-dwell time. Exact-gap inspection/rebasing now locates the inner
V6 header, preserving HOPS and GLRT bytes.

An ordering audit found that FINAL could otherwise overtake the last IQ frame
between collection and wrapping. Each accepted carrier is now reserved under
the hop-state lock. Active or reserved-carrier drains return EBUSY; an atomic
ready gate prevents active-capture drain attempts from taking the collector
mutex. The final drain becomes available only after carrier encoding, including
cancellation interleavings. No extra IQ/refill is used to deliver the tail.

## Verification

| Check | Result | What it proves |
|---|---|---|
| Focused Leo suite | 249 passed | Native worker/pool, request/frame codecs, source binding and standalone host-reader regressions |
| New SDK/request subset | 44 passed | Whole-dwell and delayed input, fractional pilot parity, hostile requests, gaps, queue saturation and worker death |
| LIBIIO Python suite | 63 passed | Existing bindings and real-network drain regression coverage |
| C regressions | 17 suites passed | Hop, tandem, layout, queues, direct transport and separate parser/provider drain fixture |
| New actual SPF provider fixture | Passed | Both rates, real isolated worker, unchanged legacy/IQ bytes, delayed events, capacity checks, failures, exact gaps and terminal ordering |
| Provider + SDK + worker sanitizers | Passed | ASan/UBSan/leak checks with the builtin numerical backend |
| Feature-disabled desktop daemon | Builds | Optional SDK is not required by legacy builds |
| ARMv7 SDK, daemon and provider fixture | Cross-builds | Existing GCC 7.3.1 userspace toolchain compatibility; not ARM execution or timing |

The provider fixture substitutes hardware-bound IIO/gain/RSSI/device operations
only. It executes the actual OPENM provider entry, frame builder, hop engine,
bridge, SDK and worker with synthetic inputs. Injected classification failure
does not change the captured IQ or its legacy metadata. Separate native-port
pilot tests cover both rates and edges, late non-dividing blocks, counters above
2^53, and fractional epoch/CFO/score agreement with desktop.

The first fixture compile exposed mismatched const qualifiers in mocked
register-I/O declarations; those mocks were corrected without widening the
production API. The terminal ordering issue and its regression tests are
retained. No numerical threshold, algorithm search or golden fixture changed.

The [receipt](evidence/2026_09_08_scanner_glrt_provider/receipt.json) retains source
commits, build configurations, artifact hashes and test outputs. Local binaries
were built before source commits, so embedded git-version stamps can identify
a parent revision. They are test artifacts, not release binaries. The repeated
`12`/`34` digest values are explicitly test-only identities. Runtime release
preflight must verify actual SDK/worker/template hashes against the approved
manifest; OPENM compares configured identities and does not derive those hashes.

## Remaining work toward the full goal

1. Wire capability negotiation, envelope handling and final draining into the
   production host through narrow ports. Unsupported peers must continue
   recording with explicit unavailable classification. Preserve strict legacy
   validation and register HOPS source geometry before consuming results.
2. Test the combined real-provider/network/host path, including terminal frame
   loss, disconnects and incomplete result inventory. The separate tests above
   do not constitute this combined end-to-end proof.
3. Replay original archived block/counter/hop-event arrival sequences for
   300 seconds at each rate. Measure additional history-copy cost, backlog,
   wall latency and system contention rather than extrapolating unit-test speed.
4. Resolve the previously measured 5 MS/s 113.47 ms p99 CPU and initial execution
   tail. This checkpoint makes no new ARM performance claim.
5. Qualify positive decisions and whole-dwell absence independently on fresh
   frozen evidence. Current results remain `unqualified_classifier`; the
   known development false flags are not solved by successful transport.
6. After software gates pass, request bounded live disabled/enabled comparisons
   on an approved spare. The excluded serial remains out of scope. No duty
   reduction, IQ loss or delayed hopping is an acceptable final result.

The full requested realtime classifier with unchanged duty remains unfinished;
this checkpoint is the provider connection, not a substitute completion goal.
