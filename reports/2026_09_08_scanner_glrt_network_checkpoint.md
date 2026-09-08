# Scanner GLRT: actual provider-to-host network checkpoint

2026-09-08. **Offline integration verified; not a deployed or qualified realtime
Starlink classifier.** No radio was accessed, no RF collected, and no FPGA,
kernel, flashed firmware, installed dependency, or production service changed.

## Outcome

The actual SPF provider, hop state machine, isolated GLRT worker, iiOD parser,
TCP transport, libiio Python binding, strict raw metadata reader, persistent-hop
session, and Leo result adapter now execute together in one bounded loopback
fixture. Full 300-second device-counter spans pass through the concrete PPU
backend at both scanner rates. Both streams deliver **2,480/2,480 unqualified
result records**, with complete terminal accounting and no missing IQ reported
by the synthetic source's validated capture receipts.

This closes the previously missing combined transport test. It does **not**
close original-arrival replay, detection-quality, ARM headroom, publication/UI,
or live same-duty gates. The full requested goal remains active and unfinished.

## What is real and what is substituted

Real components run without replacing their wire codecs or source validators:

1. The SPF metadata provider receives arbitrary blocks and delayed hardware
   events; its real hop engine constructs HOPS/HOPT and source-valid spans.
2. Its real GLRT SDK collects RX1, executes the actual child worker, and wraps
   existing metadata in negotiated result envelopes.
3. Actual iiOD OPENM/READBUFM/status/cancel/drain/CLOSE handlers and lexer/parser
   communicate with the real network backend and Python binding.
4. The actual raw reader validates V6 metadata, CRC and dual-RX geometry. The
   host session validates hop events, counters, visits and terminal inventory;
   the GLRT adapter binds results to their original source visits.
5. Full-span tests additionally use the actual `IioPersistentHopBackend`,
   including its independent V6/HOPS comparison, public client start,
   preparation/negotiation, terminal drain and host lifecycle receipt.

Hardware-facing buffer/refill, gain/RSSI/register and hop-device operations
are test substitutions. Pyadi layout priming and receiver-control operations
are provided through the existing public radio-factory port. No production
physical-LAN or excluded-serial gate is weakened. The only actual network
connection is to a new 127.0.0.1 listener; the fixture cannot open a radio.

The source is deliberately simple: constant nonzero RX0, zero RX1, original
counters above 2^53, non-dwell-aligned 131,072-sample blocks, and optionally
two-refill-delayed initial hop events. Its seven-sample synthetic transitions
are **not measured radio timings**. The full-span tests use the requested
one-millisecond guard and eight kernel buffers. IQ is consumed/discarded
incrementally, never retained as a gigabyte-scale test array.

These zero-RX1 inputs establish transport/session behavior, not signal
sensitivity, fractional pilot recovery, or realistic GLRT computational load.
Existing separate injected-signal tests remain necessary numerical evidence.

## Results and fault isolation

| Full production request, synthetic source | 2.5 MS/s | 5 MS/s |
| --- | ---: | ---: |
| Original counter span, samples | 750,217,357 | 1,500,417,357 |
| Valid visits / delivered result records | 2,480 / 2,480 | 2,480 / 2,480 |
| Result delivery complete | Yes | Yes |
| Qualified classifications | None | None |
| Result reason | unqualified_classifier | unqualified_classifier |

The sample clock is accelerated: these are **300-second counter spans**, not
300 seconds of RF or original wall-clock arrival replay. The visit counts and
synthetic duty must not be substituted for production scanner measurements.

Fourteen additional short integration cases cover both rates and all eight
edges, exact source intervals, delayed event delivery, enabled/disabled byte
compatibility, injected detector failure, actual child-process death, a lost
FINAL envelope, and partial-dwell cancellation. For matched short runs, **IQ,
inner V6 headers and HOPS bytes are byte-identical** with GLRT disabled,
enabled, failed, or terminal delivery interrupted. A test-only fixed stream
generation makes those comparisons meaningful; production IDs are unchanged.

Every server-side drain asserts that no refill occurs. Worker death and missing
FINAL preserve a complete IQ capture but produce explicitly incomplete detector
evidence. Partial cancellation returns unavailable/cancelled evidence and
restoration accounting rather than inventing an absence verdict. The test
discovers and kills only the fresh fixture server's own worker, then verifies
it was reaped. Server shutdown checks every receive buffer was destroyed.

## Small production binding addition

`MetadataBuffer.metadata_status_raw(capacity)` now exposes the existing opaque
status operation publicly. PPU already preferred this port but previously had
to fall back to binding-private symbols. The method bounds allocation, rejects
invalid sizes and closed buffers, preserves provider errors, and neither
refills IQ nor replaces the last frame metadata. It adds no wire schema or
new service. Twelve owned tests cover this public port.

## Verification and retained failures

| Lane | Result |
| --- | --- |
| Combined network integration | 16 passed, no skips |
| Short integration with ASan/UBSan/leak-checked server build | 14 passed; two full-span cases deliberately deselected |
| Existing standalone provider sanitizer regression | Passed |
| Leo focused regressions | 317 passed |
| PPU capture regressions | 182 passed |
| libiio Python binding tests | 73 passed |
| New Leo test Ruff / changed-file whitespace | Passed |

The instrumented server lane selects its own instrumented libiio build; the
Python client uses the ordinary library. It is not a claim that Python,
external dependencies, or ARM execution were sanitizer-qualified here.

Initial runs usefully failed: the fixture omitted status/cancel capability
attributes, then supplied a gain observation outside its IQ frame. Existing
client validators correctly rejected both; only the fixture was corrected.
The first setup error also exposed a fixture cleanup ordering mistake: its
context could close before its buffer, causing a Python process segfault on
later destruction. Setup failures now close the buffer before the context.
No scientific fixture or validation tolerance was relaxed.

Local implementation commits:

- Leo: `efad0b19d63df4a774b65da3c64cbaf650a96874`.
- libiio: `a188a70d7f8785b7f342e337655ae537bc20848d`.
- PPU reused unchanged: `606144e60d63910dfaf5902f722b950df65dc604`.

The [receipt](evidence/2026_09_08_scanner_glrt_network/receipt.json) records
commands, artifact hashes, measured counts, rejected attempts and limitations;
the [JUnit record](evidence/2026_09_08_scanner_glrt_network/network.xml) contains
the full-span properties. Test-only configured algorithm/configuration digest
strings are not release artifact attestation. Nothing was pushed or deployed.

## Next full-goal gates

1. Replay original archived block/counter/hop-event arrivals, with saved signal
   IQ and representative competing acquisition load. Accelerated zero-IQ tests
   cannot replace that evidence. Other transport modes need their own tests.
2. Resolve the existing 5 MS/s **113.47 ms CPU p99** and initial-execution tail;
   qualify detection quality on frozen holdout and interference controls. This
   checkpoint changes neither the algorithm nor its known false flags.
3. Finish explicit runtime composition and independent durable evidence/UI
   publication. Keep detector evidence separate from ordinary recording and
   dense re-analysis.
4. After software gates pass, obtain authorization for bounded live same-duty
   comparison on an allowed idle spare, then review merge/deployment/rollback.

No qualified positive or absence policy is enabled by this checkpoint. Unchanged
live recording duty remains unproven, not inferred from successful transport.
