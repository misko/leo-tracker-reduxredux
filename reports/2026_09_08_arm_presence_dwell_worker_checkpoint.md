# Whole-dwell ARM worker and fractional frame-record binding

2026-09-08. **Implementation checkpoint, not a qualified or deployed scanner
classifier.** All inputs were saved or synthetic IQ. Production acquisition,
FPGA, kernel and flashed firmware were unchanged.

## Outcome and boundaries

The isolated scanner worker now accepts a complete 120 ms dwell from one fixed
receiver, screens all six temporal intervals and performs one blind fractional
GLRT confirmation. The old 20 ms worker remains available as a regression
comparator. The numerical algorithm and decision thresholds were not changed.

A scanner-owned C adapter converts the worker's private result into the
existing versioned frame record. It adds the selected interval's integer
offset before binding the candidate epoch to its original device counter,
while retaining the fractional offset separately. A later carrier frame must
not substitute its own time or visit for the original dwell's identity.

The adapter has no enabled classification policy. NULL policy preserves
measurements as `unqualified_classifier`; enabling a threshold policy requires
separate scientific qualification. Positive classification and whole-dwell
absence have separate enable gates. Incomplete fractional work, worker failure,
busy collection and cancellation cannot silently become negative detections.

**Actual iiOD/client capability negotiation, LIBIIO transport attachment,
metadata-only terminal draining and production host/UI integration are still
unfinished.** Record conversion and wire-codec tests do not establish that
results are already travelling through the installed scanner. The known
specificity failures and the 5 MS/s CPU target also remain unresolved.

## Whole-dwell handoff

The existing three-slot producer/worker handoff is retained, without adding a
second work queue. IQ storage is now an aligned variable-length tail of the
private mapping. The whole-dwell allocation is **7,258,496 bytes**, including
three maximum-rate CI16 slots, the bounded result ring and bookkeeping. At
5 MS/s each selected-RX dwell is 600,000 complex samples, or 2.4 MB. This first
implementation reserves that maximum capacity at both sample rates. The
separate 20 ms mode still allocates only its smaller pool.

Capture copies selected-RX samples from arbitrary strided blocks into the
preallocated slot. It does not retain a DMA buffer while GLRT runs. Slot states
distinguish filling, queued, working and free. Full work/result capacity is
observable and does not block the producer. Tests exercise both receiver
offsets as a port invariant; all saved-IQ experiments use RX1, with no combining
or receiver switching.

The worker accepts only an exactly sized same-build mapping and immutable
template descriptor. It inherits no IIO handle, closes unrelated descriptors,
drops root credentials, sets `no_new_privs` and restores the parent-death signal
after the credential change. Existing CPU, address-space and wall-time bounds
remain. Two numerical workspaces cover lower and upper edges without creating
another acquisition owner.

## Replay protocol

The frozen source contains 96 complete development dwells, 48 at each sample
rate, reconstructed from six hash-checked 20 ms probes per dwell. The packer
checks sample-counter continuity, templates, rates, edges and source hashes.
It confirms the selected interval against the eight numerical fields retained
by the earlier frozen reference before creating an ARM expectation.

The private `LDP1` pack uses the existing bounded replay-record layout but
contains complete dwells. The native parent submits 32,768-sample chunks in a
burst every 126 ms. Input loading and worker initialization precede the replay
clock. Final runs stream the pack into the parent through SSH stdin, avoiding
a second radio-side scratch copy. The parent loads the bounded pack before
starting its paced clock; this is not concurrent network acquisition.

These are repeated saved-dwell scheduling tests, **not the original DMA/hop-
metadata arrival sequence**. Counter and visit identities repeat with the pack.
No RF, receive interrupts, dual-RX forwarding or live-network contention is
included. Detector coverage and numerical agreement here are not measurements
of live scanner duty or independent signal-detection trials.

## Failures retained, not hidden

1. The first 5 MS/s eight-dwell smoke took 436.95 ms CPU / 493.59 ms wall on its
   first dwell and skipped one later detector job. A repeat invocation matched
   all eight desktop outputs without skips. The cause of that initial tail is
   not established; it remains an unresolved startup/headroom failure.
2. The first 300 s eight-dwell run reported 2,381 completed jobs, but its output
   was truncated and malformed. Only 2,300 lines, including the terminal
   summary, survived instead of the expected 2,382. Verification rejected it.
   The old harness ignored stdio errors, allowing a successful exit despite
   lost evidence. The small `/tmp` capacity must also accommodate the unlinked
   shared-memory backing file while it is mapped: a transferred pack plus the
   7.26 MB mapping left insufficient log headroom. Capacity accounting points
   to scratch exhaustion, but the old code did not retain the write errno.
   Output corruption was already
   present on the radio; retrieved and remote SHA-256 values matched.
3. The harness now checks stream errors while emitting results and explicitly
   flushes/checks stdout before reporting process success. A `/dev/full` test
   requires a nonzero exit. The transferred pack copy was removed only from
   the experiment's owned scratch directory; the original local pack and
   archival inputs remain intact. Final runs use streamed inputs and the
   corrected parent. The rejected run is not used as a complete timing result.

## Final verification

Both corrected 300 s runs pass strict output verification: **4,762/4,762
results match desktop**, including all candidate fields, nuisance evidence,
both proposal screens and selected confirmation interval. Each rate uses all
48 development dwells, repeated to fill the paced workload. Neither run skips
work or drops results; the result ring and work slots are empty at shutdown.

| Final full-dwell worker replay | 2.5 MS/s | 5 MS/s |
|---|---:|---:|
| Completed / submitted | 2,381 / 2,381 | 2,381 / 2,381 |
| Detector CPU p50 | 53.93 ms | 99.18 ms |
| Detector CPU p99 / maximum | 64.54 / 69.73 ms | **113.47 / 119.85 ms** |
| Detector wall p99 / maximum | 68.26 / 76.89 ms | 117.58 / 123.39 ms |
| Copy-to-result p99 / maximum | 72.63 / 81.60 ms | **126.62 / 138.07 ms** |
| Maximum collector copy wall time | 7.18 ms | 12.33 ms |
| Maximum occupied slots | 1 | 2 |
| Pacing duration / total elapsed | 300,000 / 300,006.22 ms | 300,000 / 300,010.97 ms |

The 5 MS/s detector alone misses the 100 ms p99 CPU target. Its end-to-end
p99 exceeds one 126 ms arrival interval, and the pool briefly holds two jobs.
This run completes without sustained backlog, but it does not establish
headroom under real capture/IRQ/network load. Initialization and loading are
excluded from these timing distributions; the earlier initial-execution tail
remains recorded separately. Final drain time is not part of RF duty.

The final focused component suite passes **1,013 tests**, including standalone
frame binding and independent re-verification of retained evidence. Coverage includes
both worker modes, split/strided copies, immutable inputs, gaps, invalid packs,
queue saturation, process lifecycle, explicit unknowns, C/Python codecs and
host binding. The first broad invocation omitted `FFTW_PREFIX` and correctly
failed 25 explicitly marked setup cases; the rerun with the dependency present
passed them. No scientific fixture or tolerance was relaxed.

Sixteen saved-dwell executions through the final native parent and instrumented
worker pass ASan/UBSan/leak checks and match the FFTW desktop reference. The
instrumented worker uses the builtin numerical backend, so external FFTW code
is not covered by that sanitizer statement. Separately, 72 synthetic converted
frame records from an actual ARM executable decode correctly with the Python
contract, spanning both rates/edges, all six intervals and counters up to the
uint64 boundary. The same frame fixture passes desktop ASan/UBSan/leak checks.

Build identities, compressed raw outputs, rejected-run evidence and strict
verification summaries are retained in the [evidence directory](evidence/2026_09_08_arm_presence_dwell_worker/).
No raw IQ or executable binary is committed. No live-duty or classifier-quality
gate is inferred from these results.

## Next integration gates

1. Connect the result adapter to the negotiated iiOD frame envelope, preserving
   legacy framing and ensuring results from earlier dwells retain their source
   identity. Finish the metadata-only terminal drain; the existing client
   rejects zero-IQ frames, so this cannot be added without explicit negotiation.
2. Replay original archived block/counter/hop-metadata arrival sequences through
   that provider/client path, including overload, cancellation and worker death.
3. Resolve the initial execution tail, 5 MS/s CPU budget and classification
   specificity on newly frozen controls and untouched scans. Never enable the
   post-hoc score threshold merely because it rejects already-known failures.
4. Only after software gates pass, request a bounded live disabled/enabled
   comparison on an approved spare. New RF collection, deployment and a claim
   of unchanged recording duty are not authorized or established by this test.

## Reproduction

Use the project Python environment, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=src:.`
and `OPENBLAS_NUM_THREADS=1`. FFTW tests additionally require the explicit
`FFTW_PREFIX` used in their build receipts; they fail rather than silently skip
when it is absent.

- Build matching desktop/ARM whole-dwell libraries and workers with the frozen
  hybrid/integer-fold flags and explicit FFTW options. Build receipts identify
  source, compiler, dependency and executable hashes.
- `python -m tools.qualify_presence_dwell_worker prepare SOURCE OUTPUT LIBRARY
  RATE` validates and packages the complete bounded inventory. `--maximum 8`
  is an explicitly labelled first-in-source-order smoke subset, not selection
  on detector output.
- Run the native parent with `WORKER TEMPLATES PACK DURATION_MS`, using
  `/dev/stdin` for a streamed pack. No mode opens IIO or collects RF.
- `python -m tools.qualify_presence_dwell_worker verify MANIFEST RAW OUTPUT
  DURATION_MS` requires every expected result, exact identities, complete
  diagnostics, numerical parity and terminal accounting. Total timing must
  include the whole-dwell screen and selected confirmation.

The identity-attested replay target was the idle spare
`104000b29905000e17000800065934759d` at `192.168.1.15`; the excluded device was
not accessed. The radio's existing FFTW library was reused without installation.
