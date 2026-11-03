# Proposed session-bound compatibility integration

The named compatibility module is component-qualified but is not selected by
the application. The next integration should remain additive and explicit.
The portable `fractional_support` path remains the default, and no persisted v1
record gains a new interpretation.

Add a neutral `SupportDerivationPort` beside the runtime support types. The port
contains borrowed context, one synchronous callback, and borrowed profile-name
and manifest-digest views. A successful callback returns numeric `Support` and
the four factorial-moment lexemes together. It returns a small status enum and
must catch concrete implementation exceptions at the adapter boundary. The
generic port must not import `server_compat`, Python, storage, or application
types.

The first integration keeps derivation on the current serialized scanner event
callback. `Analysis::event` calls `Session::accept`, which owns the timing
snapshot used by `ingest::project_event`; moving work to the analysis thread
would require a new value-owned timing snapshot contract and is outside this
slice. The `SupportDeriver` context therefore lives at least as long as the
Session, is called only by that serialized producer callback, and is detached
only after scanner callbacks have stopped. The analysis owner never calls the
same instance. This satisfies the instance's single-owner contract without a
hidden lock or thread-local state.

That safe placement has a measured cost: the physical ARM derive-only benchmark
over the first 1,024 retained DS9 candidates measured 842 misses at 9.547 ms
mean, 10.119 ms p95, and 10.809 ms maximum, while 182 cache hits averaged
4.239 us. Because the scanner serializes sink callbacks under its output path,
an uncached derivation can extend that hold by about 10 ms. The opt-in path must
measure callback duration, detector-delivery latency, queue drops, and source
continuity before any continuous qualification. It must not move projection
away from timebase ownership merely to conceal this cost.

The session copies the profile binding once at construction and borrows only
the callback context for its documented lifetime. A nonportable session rejects
an absent callback, empty or malformed binding, changed binding, derivation
failure, non-finite numeric output, or a mismatch between numeric moments and
the supplied lexemes. There is no profile string on each `Observation`.
The concrete adapter owns one `server_compat::SupportDeriver`; callers create it
and complete constructor preflight before any radio preparation or source open.

Add a projection overload that accepts an already derived numeric `Support`.
The current projection function remains a byte-identical wrapper that calls
portable `fractional_support`. Add an ingest overload that invokes the neutral
port, calls the supplied-support projection overload, and returns the moment
lexemes alongside the `Observation`. The existing ingest overload remains the
portable wrapper. Neither layer knows the concrete profile.

For the opt-in constructor only, `Session::Pending` stores the corresponding
`pipeline::SupportAuthority`. `consume()` uses the Coordinator's existing
explicit-support ingest overload. The existing constructor and pending path
continue to call `derive_support_authority(observation)`, preserving current
portable behavior. A Session is immutable with respect to profile selection;
changing profile or manifest requires a new stream generation and Session.

The application switch should name the exact profile and require the exact
manifest digest. It should fail during argument/configuration validation if the
optional DSO, manifest, locale, rounding mode, or adapter is unavailable. It
must emit the selected profile and manifest in a new diagnostic schema rather
than changing a published v1 authority record. Historical supplied authority
continues to mean supplied metadata; it is never silently relabeled as freshly
derived compatibility authority.

The integration gates are:

1. Existing portable projection, ingest, online, Session, replay, and live
   outputs remain byte-identical when no port is supplied.
2. Constructor binding mismatch, callback error, missing DSO, environment
   failure, and mixed-session profile tests fail before evidence is accepted.
3. The opt-in path reproduces all 11,747 DS9 numeric supports and lexemes, then
   directly reproduces support digests, partition seeds, observation vectors,
   and masks for the 58 membership-identical tracks without supplied graph
   authority.
4. Host, sanitizer, QEMU ARM, and bounded physical ARM tests measure integrated
   callback latency, queue behavior, and continuity. The current 92.132-second
   physical DS9 component run and 10 ms miss latency are not an integrated
   real-time qualification.
5. Optional application packaging includes the LGPL notice, corresponding
   source, build script, and relinking instructions with the separately
   replaceable pow3 DSO.

The six C4 duplicate-rank identity ties stay explicit and outside C3. Exact C3
authority for the 58 membership-identical tracks does not establish complete
strict pipeline parity.
