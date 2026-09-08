# Scanner GLRT: runtime opt-in, durable evidence and UI

2026-09-08. **Offline implementation checkpoint; not a deployed or qualified
realtime Starlink classifier.** No radio was accessed, no RF collected, and no
FPGA, kernel, flashed firmware, production service or remote branch changed.

## Outcome

The normal persistent-hop scanner can now explicitly request the existing
RX1 GLRT metadata extension, publish the returned evidence separately from its
IQ capture, and expose it through a read-only API and scanner UI panel. The
default remains disabled. Unqualified measurements remain unavailable
classifications; raw scores do not become Starlink or no-signal labels.

Implementation commit: `353bb1995dc06ce3d5744f01bb6699cf05ee4220`.
The [execution receipt](evidence/2026_09_08_scanner_glrt_runtime/receipt.json)
retains exact commands, source identities, JUnit hashes and limitations.

This closes the missing local runtime-composition/publication/UI implementation
identified in the [network checkpoint](2026_09_08_scanner_glrt_network_checkpoint.md).
It does not close detector qualification, ARM timing, original-arrival replay,
release packaging, or live unchanged-duty verification. Nothing is enabled on
the installed scanner by this commit.

## Explicit host opt-in

The existing scanner must already be enabled in `persistent_hop` mode. Its
300 s duration, 120 ms dwell, 1,200 s cadence, both recording receivers,
rate schedule, bandwidth/IF, block sizes and transition guards are unchanged.

| Environment setting | Meaning |
| --- | --- |
| `LEO_SCANNER_GLRT_MODE` | Default `disabled`; the only admitted opt-in is `unqualified-evidence` |
| `LEO_SCANNER_GLRT_ALGORITHM_SHA256` | Required nonzero lowercase 64-hex requested algorithm identity |
| `LEO_SCANNER_GLRT_CONFIGURATION_SHA256` | Required nonzero lowercase 64-hex requested configuration identity |
| `LEO_SCANNER_GLRT_DRAIN_BUDGET_SECONDS` | Optional finite budget greater than zero and at most 10 s; default 5 s |

Orphan GLRT parameters in disabled mode are rejected. The terminal drain is
the existing negotiated metadata-only operation, not extra acquisition or a
new wait inside each dwell. Serial attestation, the physical `192.168.1.*`
restriction and exclusion of `104000bac4950008230026001b440a003a` remain intact.

These settings request identities; they are **not proof that deployed binary
files match those identities**. Release-local SDK, worker and template packaging,
file-hash attestation, compatible dependency pins and approved deployment remain
separate work. Unsupported peers preserve legacy capture and yield explicit
unavailable evidence. This table is configuration documentation, not a live
rollout instruction.

## Publication cannot take ownership of acquisition

The backend follows the existing capture lifecycle through radio close,
alternate-iiOD cleanup, immutable IQ publication and ownership release. Only
then does it read the radio's retained public evidence and publish a separate
`ScannerGlrtPublicationV1`. It never places filesystem publication in refill.

The publication binds the public capture session and manifest digest to the
requested algorithm/configuration and existing session-evidence contract.
Before publication and presentation, validators compare the wire session,
terminal visit inventory, RX, rate, channel/edge and exact source-counter bounds
against the public IQ receipt. Existing capture/frame/session contracts are
unchanged. Fractional offsets stay separate from uint64 epoch anchors.

Storage owns the new `scanner-hop-classifications` namespace. One immutable
checksummed JSON file is published by a no-overwrite atomic link, with explicit
file and directory synchronization. Reads are bounded to 4 MiB and reject
symlinks, nonregular files, corrupt checksums and unsafe identities. Read-only
construction creates no directory. QNAP paths are rejected before access.

Failure handling is deliberate:

- Invalid or missing detector evidence becomes an explicit error publication.
  Unsafe nested model copies are revalidated before accepting measurements.
- A result-store failure leaves already published IQ intact and emits a warning.
- A capture retry reads the original evidence; it neither reopens RF nor reuses
  a radio's last-session result. Changed requested identities do not replace it.
- Injected failures before the atomic link leave no final file. A directory
  sync failure may leave a complete visible file, with a reported failure and
  unproven crash durability. Store-level retry is idempotent; it does not erase
  the visible publication. Temporary files are cleaned on ordinary return.

## Operator visibility

`GET`/`HEAD /api/v1/scanner/persistent-sessions/{session_id}/glrt` reads evidence
without running dense analysis or scanning IQ. Missing products return 404;
corrupt/stale evidence returns a generic 409. There is no write endpoint.

The scanner view has an independent **On-radio GLRT · RX1** panel, also shown
when dense analysis is unavailable. It separates result delivery from scientific
classification, reports dropped/incomplete results, and paginates 50 rows at
a time. Each row shows the source visit/channel, verdict/reason, exact score
and margin, CFO, screened versus confirmed coverage, CPU/wall time, and exact
epoch plus fractional offset. CPU time is explicitly not scanner duty.

Polls do not overlap; changing sessions aborts requests and ignores late old
responses. Missing, failed or malformed evidence is contained in this panel,
not converted into a recording failure or a negative detection. Canonical
decimal counter strings remain exact above 2^53; only small interval differences
are converted to floating point for duration display.

This is **post-capture publication**. Polling can discover a product published
after the IQ history entry appears, but there is no new live partial-product
store or per-dwell UI stream during acquisition. The existing on-radio metadata
transport remains responsible for asynchronous results during capture.

## Verification and retained limits

| Verification | Result |
| --- | --- |
| Portable backend, contract, storage, scheduler, radio-adapter and API regressions | 167 passed; one PostgreSQL test explicitly deselected |
| Included new publication/runtime tests | 36 passed |
| Full web unit/DOM suite | 104 passed across seven files; includes 21 new panel tests |
| TypeScript and production web build | Passed |
| Changed Python Ruff and whitespace | Passed |
| Concurrent immutable publication and maximum 2,500-result inventory | Passed |
| Injected file-sync, atomic-link and directory-sync failures | Passed; original IQ verified unchanged |

The initial broader Python invocation retained **165 passes and one setup
error**: `LEO_TEST_DATABASE_URL` was not configured. The existing explicitly
marked database test refused before connecting. The final portable invocation
uses `-m 'not postgres'`; no database-backed or production-browser E2E pass is
claimed. No marker, dependency gate, scientific fixture or tolerance was relaxed.
The original failed JUnit output is retained losslessly compressed, including
pytest's traceback whitespace; both compressed and original hashes are recorded.

Web tests emitted the existing jsdom WebGL/canvas diagnostics from SkyView.
The build emitted a large SkyView-chunk warning. Both processes exited zero;
these warnings are retained rather than represented as silent clean output.

Runtime capture fixtures retain one synthetic dwell and cancel via the public
capture API. They exercise real compressed IQ publication and cleanup ordering,
but are not full qualified RF scans. The 2,500-result test establishes storage
capacity only, not source-attested acquisition or detection sensitivity.

## Remaining path to the requested goal

1. Reduce the measured 5 MS/s CPU/startup tail and retest on saved data. The last
   actual ARM measurements remain 113.47 ms CPU p99 and 126.62 ms copy-to-result
   p99 at 5 MS/s; this checkpoint provides no new timing claim.
   The subsequent [execution optimization checkpoint](2026_09_08_native_presence_execution_checkpoint.md)
   reduces desktop setup/allocation and recurring CPU, with 475 passing tests;
   ARM timing and live duty remain unverified.
2. Qualify detection with frozen held-out recordings and valid interference
   controls. The [decision checkpoint](2026_09_08_arm_presence_decision_checkpoint.md)
   retains the short-burst and reference-association limitations; no threshold
   policy is enabled here.
3. Replay original block/counter/hop arrivals with competing capture load,
   then complete reviewed userspace release packaging and rollback checks.
4. After software gates pass, obtain explicit authorization for bounded live
   disabled/enabled comparisons and verify unchanged duty before promotion.

The full objective remains active and unfinished. Software publication success
does not substitute for qualified every-dwell detection and measured live duty.
