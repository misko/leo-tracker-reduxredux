# Native adaptive scanner composition

This directory is the bounded application slice that joins the local PLUTO+
source, the timed-window assembler, the continuous variable-dwell scan policy, the established
energy feedback classifier, and a bounded native fractional-GLRT executor. It has no
Python, server, database, network-IQ, USB-IQ, or reference-checkout runtime
dependency.

`scanner.h` is the C boundary. The caller opens and primes an exclusively owned
`leo_local_source`, supplies a detector port, and receives serialized event
callbacks. A run requires both a counter-duration bound and a visit-count bound.
Duration is capped at 30 minutes. It also requires an absolute CLOCK_MONOTONIC
wall deadline. A normal watchdog thread invokes the source's mandatory
cooperative cancellation callback to interrupt a blocked refill. The source
callback must actually unblock acquire; the detector and event sink must return
within the caller's deadline budget because their ABIs are not preemptible.
`duration_ms` remains the source-counter admission bound and does not conceal
callback overrun. The CLI starts its wall deadline before template, detector,
radio preparation, local-source, and prime setup; it checks setup elapsed time and uses cancellation
for prime and capture. No signal handler calls libiio or scanner APIs.

`leo_scanner_run_timed` is an additive counter-acquisition composition for a
measured counter/UTC adapter. Its callback runs synchronously on the caller's
acquisition thread once for the policy origin and immediately before every
policy selection, never while a DMA block is leased. The callback's returned
coherent counter is the sole counter used for that decision. A negative error
fails closed before selection or retune at that boundary; unexpected positive
statuses become `-EIO`. The original `leo_scanner_run` entry point retains its
direct local-source snapshots and unchanged behavior. Counter callbacks are
cooperative and cannot be preempted by the source-cancellation watchdog.

`scanner_source.h` adds a source-neutral entry point over `leo_source_port`.
It leaves `scanner.h`, its event bytes, and both legacy entry points unchanged.
The caller declares the counter and position semantics, required source and
transition attestations, frequency tolerance, and whether the source must meet
the physical-counter capability profile. Requirements are checked before the
policy origin or first selection. Every generic event wraps the original event
with its counter, position, time, transition, block, and physical-counter
authority. `physical_counter_qualified` describes only the source coordinate;
it does not attest UTC, projection, or end-to-end revisit timing.

The strict local wrapper obtains the immutable configuration actually used to
open the opaque local source and creates the existing local port adapter. It
never constructs a second configuration ceiling. If provider release fails,
the generic port retains the lease for an explicit cleanup retry. If that retry
also fails in the legacy wrapper, adapter bookkeeping is disposed while the
lease remains in the caller-owned local source; the mandatory source close
makes the final provider release attempt. The scan reports the cleanup error.

A caller may explicitly admit a software-delivered ordinal for recorded replay,
including a zero profile CRC when no CRC attestation is required. Such events
remain `physical_counter_qualified == 0` and cannot be supplied to the live
Timebase as exact coordinates. The source-neutral scanner still requires two
simultaneous coherent receivers at 2.5 MS/s. Generic single-RX,
unsynchronized dual-RX, and USB hardware profiles remain unsupported until a
provider proves the required capabilities.

The initial fake-tested composition rate is
2.5 MS/s with two synchronous receivers. Inactive targets use 120 ms. Once
ACTIVE feedback is accepted and applied, that target uses the configured
120/240/360 ms active-dwell ceiling. Feedback also preserves the original
target-weight boost and decay behavior.

The policy feedback lane preserves `ci16-mean-complex-power-v1` exactly:

1. use every I and Q component of physical RX1 in a complete visit;
2. compute mean component power, `(sum(I^2 + Q^2) / (2*N))`;
3. express it as `10*log10(mean / 32768^2)` dBFS; and
4. classify ACTIVE at or above -38.0 dBFS, otherwise QUIET.

An incomplete visit is explicit UNKNOWN evidence and is ineligible for policy
feedback or GLRT. This feedback remains independent of GLRT candidates, so the
adaptive policy has not silently changed.

The window assembler validates the first 20 ms at each 120 ms probe position.
The detector receives a separately retained, bounded copy of the complete
dwell because its API requires the full 120/240/360 ms input. Legacy entrypoints
retain exactly one detector worker. The additive `leo_scanner_run_ex`,
`leo_scanner_run_timed_ex`, and `leo_scanner_run_source_ex` entrypoints borrow
one to four caller-created detector contexts and bind each executor worker to
one stable context. Their queue and dwell slots are bounded at setup;
overload emits `LEO_SCANNER_QUEUE_DROP` rather than blocking capture or hiding a
missing analysis.

The application chooses the worker count as part of its shared CPU budget; the
scanner never defaults it from the machine's core count. New entrypoints require
nonnull, distinct contexts even for one worker and validate all bindings before
the first source callback. Every binding reports identical capabilities and has
the same nonzero `configuration_digest`. That digest is caller attestation over
the detector build/algorithm, sample rate, exact/control template hashes, and
selected mode. The scanner compares attestation bytes but cannot verify the
actual context internals. More than one worker also requires the detector's
`process_serialized` capability to be false. Contexts and binding arrays remain
caller-owned until the call returns; construction is sequential before the run,
partial construction must be rolled back by the caller, and destruction occurs
only after return. Accepted jobs and all callbacks drain before return.

Event callbacks remain serialized. Cross-visit completion order is unspecified,
and another visit may interleave between one visit's result and candidate
events; within each visit the result precedes its candidates. Executor
`detector_queue_high_water` counts queued jobs only, excluding active workers.
The retained-IQ memory guard accounts for `queue capacity + workers + one`
dwells: queued jobs, active jobs, and the acquisition copy. Detector status
failures remain explicit per-job events and do not abort acquisition. Source,
deadline, and sink failures drain accepted jobs; detector and sink callbacks are
cooperative and cannot be force-cancelled.

The CLI queue capacity is four: one running analysis plus four queued analyses
can own five dwell slots. At the 360 ms ceiling each retained dual-RX ci16 dwell
is 7.2 MB; the conservative bounded IQ ownership check covers five slots plus
the acquisition copy, or 43.2 MB. At the qualified 120 ms ceiling that bound is
14.4 MB. The preceding 585 s queue-two run measured 24,040 KiB whole-process
maximum RSS; queue four adds at most two retained 120 ms dwells (4.8 MB) in that
operating mode. This capacity reduces measured detector bursts but does not
establish a lossless guarantee; every overload remains explicit.
It also increases bounded drain latency: at the observed 401.733 ms maximum
detector service time, five outstanding jobs can approach 2.01 s before drain.
Detector and sink callbacks remain cooperative and nonpreemptible. Existing C9
saved-IQ pacing with one worker and four queue entries validates executor
backpressure; it does not prove live scanner losslessness. A 60 s RF run is an
integration smoke only.

Candidate events retain the native ordinary and fractional values. The detector
capability `fractional_epoch_server_parity_qualified` is copied into every
detector event. It is currently false: implementation and structural coverage
do not establish server parity or production scientific equivalence.

The local counter is the only time authority in this slice. No event invents a
UTC timestamp. A later timing adapter must provide a measured counter/UTC
bracket before observations can carry UTC.

This component stops at candidate evidence. It does not project C3 physical
observations, build tracks, or run IQ-to-location inference. Target identity and
the attested post-recall profile CRC/frequency remain explicit in every event;
the CRC is required to be nonzero but may legitimately change during recall.
The tuned frequency must remain within the firmware-qualified 2 Hz tolerance.

`leo-adaptive-scanner` is safe by default. With no arguments it prints its
capabilities and performs no RF operation. RF capture requires the literal
`--capture` flag plus explicit duration, visit limit, templates, and targets:

```text
leo-adaptive-scanner --capture --duration-ms 300000 --maximum-visits 2000 \
  --active-dwell-ms 240 --block-ms 20 \
  --exact-template exact.c128 --control-template control.c128 \
  --target 0 2400000000 [--target PROFILE FREQUENCY_HZ ...]
```

`--block-ms` is explicit because it controls capture duty cycle rather than
policy science. The 20 ms geometry uses 50,000 samples per receiver and exactly
tiles every supported 120/240/360 ms dwell. The retained 120 ms option uses
300,000 samples and can discard up to one full DMA block at each retune because
leased block tails cannot cross a frequency transition. Live qualification of
that geometry observed roughly 240 ms between consecutive 120 ms visits. Use
20 ms for qualification; 120 ms remains available for controlled comparison.
Both geometries retain the same transition budget, policy, feedback threshold,
and detector windows.

The physical Fast Lock settling interval remains 20 ms. Before each selection,
the scanner takes a fresh firmware source-counter snapshot rather than using
the preceding DMA watermark. Policy admission uses a distinct 100 ms execution
allowance, based on a measured 95.8832 ms maximum interval from valid end to the
next valid start under concurrent detector and location load. This allowance is
not an RF settling interval. The policy revalidates the actual committed start
against the selected target's 3 s deadline and every remaining EDF deadline.
Unexpected delivery beyond the reserved allowance therefore fails closed with
`-ETIME`; it never relaxes the maximum revisit interval. The concurrent
background location worker runs at nice 19 in the qualified composition so it
does not compete at equal priority with acquisition.

Visit JSONL records include the policy selection counter, firmware recall
before/after counters, whether a recall occurred, the resulting validity
interval, energy sum/sample count, classifier windows, and outcome. A recall
that completes within the nominal 20 ms budget shares that budget; a later
completion receives a full 20 ms settling interval after its measured end. A
consecutive visit to the already-current profile skips recall and adds no
manufactured transition interval, matching the maintained session contract.
Detector records add monotonic enqueue/start/finish, derived queue/runtime, and
row count. Non-finite scientific floating values serialize as JSON `null`.
The final summary reports every scanner counter, an explicit stop reason and
status, selected block geometry, and every cleanup phase status.

The CLI reserves the counter-device session before bufferless setup, prepares
paired RX at 2.5 MS/s, 2.5 MHz bandwidth, manual 40 dB gain, and 16 kernel
buffers, then generates target CRCs from the compiled profile bytes. It
activates the firmware owner only for capture. After source-close it deactivates
that owner, restores the original RX state under the still-held reservation,
and closes the reservation. Any restoration failure makes the command fail and
prints phase-specific status; the library preparation handle remains retryable.
The counter-session reservation excludes other counter/tandem sessions but does
not block arbitrary local or network IIO writers. Controlled deployment must
ensure no such writer runs during preparation or restoration; firmware capture
ownership provides the stronger exclusion only during active capture.

The CLI uses ordinary GLRT plus the additive fractional epoch lane and emits
JSONL visit, drop, failure, result, candidate, acknowledgement, and summary
records. It restores the pre-scan frequency through the local-source owner on
all normal and error exits.

One CLI process owns one exact/control template context. Every `--target` in
that invocation must therefore use the same waveform/edge template identity;
the present operational shape is one edge across four channels. A mixed lower
and upper eight-target invocation would require separate declared template
contexts and is not implemented here. Channel, edge, RF conversion, and UTC
belong to the later online coordinator/C3 projection; this candidate-only CLI
does not infer them from an IF tuning frequency.

Builds require the source-owned detector archive and its pinned FFTW libraries:

```bash
LEO_DETECTOR_STATIC=/absolute/libleo-adaptive-detector.a \
LEO_FFTW_FLOAT_STATIC=/absolute/libfftw3f.a \
LEO_FFTW_DOUBLE=/absolute/libfftw3.so \
native/adaptive/scanner/build.sh host /absolute/output
```

Set `LEO_SKIP_SCANNER_CLI=1` to build and test the injectable core without the
numerical detector linkage. `host`, `sanitize`, and `tsan` execute the reproducible
fake-provider suite, including the exact active/quiet threshold, 120-to-240 ms
ACTIVE dwell transition, counter gap, changed/zero CRC, out-of-tolerance tune,
blocking-refill cancellation, queue-one overflow, the queue-four
five-outstanding bound, worker callback failure, and timed-counter acquisition
thread/lease ownership, exact policy-counter propagation, fail-closed initial
and selection refresh errors, and the legacy snapshot path.
The suite also compares the exact dual-RX common-port path with the legacy local
path, rejects missing capabilities and malformed profile/authority requirements
before selection, exercises explicitly unqualified software ordinals, suppresses
analysis after overflow or an unknown discontinuity, and proves cancellation and
retained-lease cleanup failures. This is CPU-only provider qualification; it is
not a USB-device, UTC, RF, or end-to-end scientific qualification.
The suite also covers one, two, and four versioned detector bindings, distinct
worker routing, four-way overlap, queued-only high water, per-job detector
failure, partial validation before any source operation, and no callback after
return. Set `LEO_REAL_DS9_TEST=1` with the detector and FFTW paths to compile and
run the recorded-data test. It compares two positive DS9 dwells through one and
two detector contexts, keyed by visit, and requires exact source/science event
bytes after explicitly clearing only the five monotonic detector timing fields.
`arm` cross-compiles the core library, CLI, and the same test binary; the
two executables statically link libstdc++ and libgcc while libc, libm, pthread,
libiio, and double-precision FFTW remain target shared libraries.
