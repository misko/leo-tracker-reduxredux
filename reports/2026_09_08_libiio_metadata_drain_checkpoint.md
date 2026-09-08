# LIBIIO metadata-only result drain checkpoint

2026-09-08. **Transport implementation, not a deployed scanner classifier.**
The active objective remains complete 120 ms single-RX Starlink dwell
classification carried in LIBIIO frame metadata without reducing recording
duty. This checkpoint addresses terminal result delivery; it does not reduce
that objective to a standalone metadata API.

## Implemented

The libiio integration branch now contains commit
`27817353ee6b031d67454860ce1659837fb4866d`, based on remote master
`c752ab684a4c9924ee362ccfb02a7ac65f7992f9`:

- Public `iio_buffer_drain_metadata()` and optional Python
  `MetadataBuffer.drain_metadata()`.
- An API-v10 optional backend callback and network capability
  `iio,buffer-metadata-drain=1`.
- An explicit `DRAINBUFM device capacity` command on the owning OPENM
  connection. The existing refill operation still requires IQ.
- An optional session-owned provider callback, so old metadata providers need
  no additional required symbol. Advertising transport support alone does not
  advertise a classifier or opt a session into classification.
- Bounds of 1..65536 bytes, strict length parsing, and connection invalidation
  after malformed or partial framing. Complete pending/error replies preserve
  the transport and can be retried by the session owner.

No OPEN, IQ refill, channel-mask change, hop scheduling or detector computation
occurs inside the drain operation. It does not overwrite the previous refill's
IQ or metadata. The client rejects pending direct-async replies, unread cached
frames and failed batches. iiOD looks up only the requesting session's device
and pins the provider through the callback, then unlocks before transmission.

## Verification

| Check | Result | Scope |
| --- | --- | --- |
| Desktop C suites | 9 passed | New drain client/server plus batch, lease, command, hop and affinity regressions |
| Python binding suite | 63 passed | Includes 10 real-network-backend loopback tests |
| Existing Leo fractional frame/host suites | 148 passed | Existing codec, result adapter, contract and host-reader regressions |
| ASan/UBSan/leak checks | 3 C suites passed | Drain parser/provider, direct transport and metadata batch core |
| Instrumented library with Python | 10 network tests passed | ASan/UBSan; Python-process leak detection disabled |
| ARMv7 build | Passed | GCC 7.3.1; same userspace source, no firmware build/change |
| Actual spare ARM execution | 2 C suites passed | Synthetic parser/provider and direct transport; no receive buffer opened |

The C server fixture uses the actual generated lexer/parser, handler and
client around an XML-only device and synthetic already-open session. The
network tests separately exercise the actual Python/C/network backend against
a loopback-only peer. Neither fixture emulates radio timing or the Starlink
classifier. The existing full acquisition e2e executable was built but not run
against hardware. Mixed historical client/server binaries were not qualified;
tests cover legacy framing, old backend API guards and missing capability.

Coverage includes late results, pending work, final marker/exhaustion,
small capacity without consuming a result, session opt-out, wrong owner,
provider teardown, malformed capacities, length overflow, truncated payloads,
maximum-size opaque binary payload, poisoned connection and unchanged IQ.

The ARM target was the serial-attested idle spare
`104000b29905000e17000800065934759d` at `192.168.1.15`. Only two synthetic test
executables and a private libiio library were copied into an owned temporary
directory. Runs used nice 19, a 10 s CPU bound, 128 MiB address-space limit and
15 s in-process wall alarm per executable. All radio buffers were checked idle
before and after. The excluded device was not accessed.
The three owned radio-side files and their empty temporary directory were
removed afterward; local builds and evidence remain available. The spare's
pre-existing wall clock is not a recording-time reference for this experiment.

ARM artifact SHA-256:

| Artifact | SHA-256 |
| --- | --- |
| libiio.so.0 | `d9a0c59f7e937b5f9b8b03431f2bea0a65eb3301eb0184c795071a3b1576fb8e` |
| Server/parser fixture | `ed6caff6e17dab6377cd2be36e3ae6a704a4c99d3d03a74c8fc3e696095eacd2` |
| Direct transport fixture | `94544103d2feea5eedd2ac0914ac60edaf3d29b32b4ac1776215078fc09bb931` |

Artifacts were built from the final source before committing; their embedded
git-version stamp can identify the parent, not the new commit. These are test
artifacts, not production release binaries. Raw ARM output and compact test
receipts are retained in [the evidence directory](evidence/2026_09_08_libiio_metadata_drain/).

## Failures found and corrected

1. The first actual network test returned ENOSYS: the new callback existed but
   the network context still reported backend API v9. Updating the context to
   v10 fixed it; the real-network regression remains.
2. The legacy lexer's catch-all discarded `+` in a malformed capacity, allowing
   the remaining digits through. The new command uses dedicated lexer states
   to retain/reject the complete capacity token without changing legacy rules.
3. The first server fixture build exposed conflicting iiOD/client private
   headers. Test-side client glue now lives in a separate translation unit;
   no production private API was widened to accommodate the fixture.
4. An initial SSH attestation command was incorrectly quoted and failed; no
   test or RF action ran. The corrected command positively attested the spare.
5. The first ARM test invocation failed because the spare lacks `timeout(1)`;
   no tests ran in that invocation. Both fixtures now own a bounded wall alarm,
   and the corrected ARM execution passes. The failed attempt is retained.

The desktop build also reports a pre-existing libxml2 `xmlMemoryDump`
deprecation warning. Its initial configuration lacked optional Avahi discovery
dependencies; explicit DNS-SD disablement produced the isolated test build.
No scientific fixture or tolerance was relaxed.

## Remaining integration and release gates

The real SPF scanner provider does **not yet** advertise or accept a GLRT OPENM
request, attach worker results to subsequent legacy-frame envelopes, or emit
GLRT DRAIN/FINAL records through this operation. The host's standalone GLRT
reader is tested, not yet connected to the production capture session.

The next implementation step is the opt-in provider connection: bind valid
whole-dwell input from original block/hop evidence, consume the bounded worker
result ring without waiting, preserve the original visit/counter/fractional
epoch in later carrier frames, and drain terminal results through this API.
Update exact-length provider/client validators via explicit envelope handling,
not by appending unexplained bytes to published contracts.

Lifecycle needs specific attention: direct-async currently retains its provider
until close, while sealed burst and ordinary DDR-ring paths can free it at
capture completion. Do not advertise unsupported modes without implementing
and testing retained-result ownership. Connection loss must leave explicit
incomplete evidence, not a successful final receipt.

After provider integration: replay original block/counter/metadata arrival
sequences; finish startup/headroom and 5 MS/s performance work; qualify
classifier specificity/recall on fresh frozen evidence; then request a bounded
live disabled/enabled comparison on an approved spare. No classifier policy is
enabled by this change. No live-duty improvement or unchanged-duty claim is
established, and no production service, firmware, FPGA or kernel was changed.
