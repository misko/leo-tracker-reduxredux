# Scanner GLRT: source-attested host integration

2026-09-08. **Implemented and tested offline; not deployed or qualified for
unchanged live scanner duty.** No radio was accessed, no RF collected, and no
FPGA, kernel, flashed firmware, installed dependency, or production service changed.

## Outcome

The opt-in host capture path now negotiates GLRT support, unwraps legacy
metadata, matches completed results to validated source dwells, and drains the
last results before closing the receive buffer. Both recorded RX streams remain
unchanged. Detector evidence is separate from existing immutable capture receipts.

Implementation commits, local only:

- Leo `11b816cb66a7fdbc21dee0d5db4f73c936245cd8`.
- pluto-plus-utils `606144e60d63910dfaf5902f722b950df65dc604`.
- Existing libiio provider `af12ce68f8bb3f101c38f0332efe157513367a27` is unchanged
  by this checkpoint; see the [provider report](2026_09_08_scanner_glrt_provider_checkpoint.md).

## Capture integration

The acquisition library exposes a small optional metadata-extension port. It
validates the original tandem/HOPR request before negotiation and uses the public
binding's metadata-only drain support. Missing capabilities, incompatible
identities, or an older host factory retain legacy capture with explicit
unavailable classification. There is no speculative second OPEN or RX buffer.

The raw reader locates the unchanged V6/HOPS bytes before running existing
metadata and IQ checks. Full envelope bytes travel in a transient wire block.
Only after session, event order, tuning, stream generation, counter continuity,
and IQ geometry validation does the GLRT adapter consume results. The adapter
keeps bounded result/geometry inventories, not IQ. Invalid classifier semantics
remain distinct from unrecoverable frame-boundary or capture errors.

Host tests uncovered an existing completion-validation gap: HOPT's last block
sequence and end counter were not checked against the actually delivered IQ.
Completion now makes those checks, as cancellation already did, before final
result reconciliation. The failed test and its correction are retained.

Results keep their original uint64 source intervals and separately represented
fractional offsets, including counters above 2^53 and all eight channel/edge
targets. Carrier-frame time never replaces source-dwell time. Claimed searched
samples beyond delivered IQ are rejected as detector evidence.

After validated terminal capture status, the adapter uses the existing session's
metadata-only drain. EAGAIN/EBUSY are retried within a finite budget; disconnect,
missing FINAL, timeout, or incomplete inventory cannot become a successful
classification. The retry budget is five seconds by default, plus at most one
already-running RPC's finite IIO timeout. This is not a hard five-second total
wall-time guarantee. No refill or fabricated IQ delivers the tail.

## Independent evidence contract

`ScannerGlrtSessionEvidenceV1` records negotiation, provenance, accepted mode,
independent terminal inventory, result sequences, losses, original per-dwell
records, final-envelope receipt, and explicit failure.

- `delivery_complete` means the full expected inventory arrived consistently.
- `classification_complete` additionally requires actual classified results,
  not unavailable work. Even a fully delivered unqualified run is not a
  qualified classifier. A zero-visit run is not a signal classification.

The current provider mode remains `unqualified-evidence`. The adapter rejects
positive/negative assertions in that mode; this checkpoint enables no threshold
policy and claims no specificity improvement. `PlutoPersistentHopRadio` accepts
explicit GLRT options and exposes the immutable final evidence and error after
producer completion, retaining them across close. Snapshot failures cannot turn
an independently valid capture into a detector-driven recording failure.

The evidence is ready for a narrow persistence consumer, but production
composition/CLI configuration, durable publication, and UI presentation are
**not implemented by this checkpoint**. The installed PPU pin is unchanged;
tests explicitly select the new local host worktree. No remote dependency is
pinned to an unpublished commit.

## Verification

| Check | Result | Scope |
| --- | --- | --- |
| Leo focused suite | 317 passed | Host adapter, codecs, session evidence, native SDK/worker/pool, persistent-hop application/contract regressions |
| PPU focused suite | 182 passed | Capture/metadata regressions; optional negotiation, source validation, fault isolation, terminal ordering |
| Native worker-to-host fixture | Both rates pass | Actual C SDK and isolated numerical worker produce raw LGC1 bytes consumed by the actual PPU session and Leo adapter |
| Ruff and staged whitespace checks | Pass | All changed source/test files in both repositories |
| Leo targeted mypy | Pass, three files | Imports skipped; not a whole-repository typing claim |
| PPU targeted mypy | Pass, five files | Python 3.12 with normal import following |

The native fixture uses synthetic dual-RX CI16, deliberately loud RX0 and zero
RX1, non-dividing chunks, and original large device counters. It verifies the
unchanged IQ streams, selected RX, source-result association, complete delivery,
and drain-before-close. Existing native-port tests in the same focused suite
cover fractional injected-pilot output. The new fixture does **not** execute the
actual SPF provider or network transport; their combined path remains a gate.
No ARM runtime or live-duty measurement was made here.

Initial test invocations exposed an undeclared local PYTHONPATH selection and a
new test fixture that violated HOPR's own safety bound. The final commands make
the dependency explicit and use a valid fixture; no fixture oracle or scientific
tolerance was relaxed. The environment's NumPy stubs could not be parsed under
PPU's Python 3.11 mypy target; the passing typing run explicitly targets 3.12,
not a verified 3.11 environment. The [receipt](evidence/2026_09_08_scanner_glrt_host/receipt.json)
records commands, results, source revisions and limitations.

## Remaining full-goal gates

1. Combine actual SPF provider, network backend, and production host, including
   interrupted final delivery and worker failure.
2. Replay original archived block/counter/hop-event arrivals for 300 s at both
   rates and measure the shared acquisition/history/transport overhead.
3. Wire reviewed runtime artifacts and explicit options into production
   composition; persist and present the separate evidence through narrow ports.
4. Resolve the 5 MS/s 113.47 ms p99 CPU and initial-execution tail, then qualify
   positive and absence decisions independently on frozen holdout/controls.
5. Obtain explicit authorization for bounded live disabled/enabled comparisons
   on an allowed spare. No reduced duty, lost IQ, or delayed hopping is accepted.
6. Review compatible release artifacts, merge, and deploy only with authority.

The full realtime classification goal with unchanged duty remains active and
unfinished. This checkpoint establishes host connectivity and truthful result
accounting, not production operation or a validated Starlink decision policy.
