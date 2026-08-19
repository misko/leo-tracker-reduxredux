# ADR 0006: J1 acceptance-evidence disposition

Status: accepted — Option B

Decision date: 2026-08-19 UTC

Authorization: the project owner explicitly instructed the Codex project task
to proceed with Option B on 2026-08-19 UTC.

## Context

Before this decision, the implementation plan required both RETRO and J1
parity before historical detector/QAM recovery was complete. In particular:

- WP5 requires RETRO and J1 fixture resolution with immutable hashes;
- the detector gate requires recovered J1 to use receiver calibration and meet
  documented tolerances; and
- R-018 names the RETRO and J1 parity gate as its acceptance evidence.

RETRO is recoverable and protected. Its exact selected IQ bytes and frozen
oracles reproduce the historical candidate epoch, receiver CFOs, QAM metrics,
and inverse-noise combined result within reviewed tolerances. RETRO remains a
known-pilot **candidate** canary; it is not a calibrated detection, specificity
measurement, signal attribution, or payload decode.

J1 is different. The read-only recovery audit in
[`../j1_recovery_audit.md`](../j1_recovery_audit.md) did not recover any of the
three immutable inputs required by its frozen acceptance claim:

| Input | Required identity |
|---|---|
| Full dual-RX CI16 IQ | 1,200,000,000 bytes; SHA-256 `23cceb3a5223180ff92398214125513d4c32cc541ec1ae5b7c4c28fba5bbcc8c` |
| Selected 41.6-second window | byte offset 832,000,000; 200,000 bytes; SHA-256 `4fbd775f850124dab038e70dadba1ce1cbbfc16ebe58d9fb425430b51d61ce02` |
| Frozen receiver calibration | SHA-256 `141a489a08f236839cd1cbec8d31cc31611abd5941b91bca7269974b53d17f8d` |

Retained J1 reports, JSON, and plots document historical observations, but they
cannot be inverted into the original IQ or establish the missing calibration
object's identity. The current and backup calibration files have different
digests. Treating any of those materials as equivalent would fabricate
provenance.

## Decision

Adopt Option B. RETRO remains the required, immutable, fail-closed historical
numerical-candidate parity lane. J1 is permanently declared
`UNAVAILABLE_HISTORICAL_EVIDENCE` unless a later exact-byte recovery review
establishes otherwise. Its expected full-IQ, selected-window, and frozen
calibration identities and its recovery audit remain part of the declared
inventory, but J1 is not executable and cannot be counted as present, run,
passing, calibrated, or silently omitted.

WP5 and revised R-018 close on the available RETRO numerical evidence plus the
reviewed, machine-validated J1 unavailability record. This is an explicit
change to the former acceptance requirement, not retroactive evidence that J1
passed. It authorizes no J1 parity, calibrated-detection, specificity,
attribution, or payload-decoding claim.

Receiver-calibrated capability is separated into a future fixture gate under
the evidence requirements below. That fixture does not yet exist, is not J1
under a new name, and is not a dependency of the present candidate-only
production acceptance gate. It becomes required only after independent review
of a concrete immutable evidence package and a subsequent change-control
revision.

## Decision options

### Option A: retain exact J1 evidence as a hard blocker

Keep the existing WP5, detector-gate, R-018, and production-gate wording
unchanged. RETRO parity is necessary but not sufficient. R-018 cannot close,
and gates that require every preceding gate cannot close, until exact J1 input
evidence is recovered and the protected parity lane passes.

J1 recovery is accepted only when one of these byte-level triggers succeeds:

1. recover the 1.2 GB object, verify its exact size and full SHA-256, then
   derive the declared 200,000-byte window and verify its exact SHA-256; or
2. recover an independently retained 200,000-byte window and verify its exact
   SHA-256, while limiting every result to slice-level parity.

A calibration-dependent J1 result additionally requires either the exact
frozen calibration object or a separately reviewed immutable calibration
authority and an explicit provenance migration. Numerical similarity to a
mutable calibration file is not recovery.

If the trigger fires, the bytes must first be copied into the protected local
TEST corpus with a new immutable fixture manifest, verified hashes, source
provenance, and an indefinite hold. Any QNAP source remains read-only. The
fixture becomes required only through a reviewed registry change; its lane
then fails closed on absence, digest mismatch, calibration mismatch, or parity
failure.

This option maximizes continuity with the original acceptance contract. Its
cost is that a permanently lost historical object can permanently prevent
R-018 and the complete production gate from closing even if all reproducible
scientific and operational behavior is otherwise qualified.

### Option B: revise the gate around available evidence

Adopt an explicit requirement change rather than pretending J1 was recovered.
The revised gate would:

1. preserve RETRO as the required immutable historical numerical-parity gate;
2. record J1 as `UNAVAILABLE_HISTORICAL_EVIDENCE`, retaining its exact
   identities, reports, recovery audit, and recovery trigger without counting
   it as an executable or passing fixture; and
3. define receiver-calibrated capability as a separate future gate requiring a
   newly acquired or recovered immutable fixture with predeclared evidence and
   tolerances.

Under the accepted Option B, R-018 is rewritten narrowly along these lines:

> Recover reproducible historical detector/QAM numerical capability from the
> available immutable RETRO evidence before novel optimization; preserve J1 as
> unavailable historical evidence and make no J1 or calibrated-detection claim.

Its acceptance evidence would be the protected, fail-closed RETRO production
parity lane plus the reviewed J1 unavailability record. The WP5 and detector
gate text would receive matching edits. Closing the revised R-018 would mean
only that the recoverable historical numerical primitives and candidate path
are protected. It would not mean J1 parity or calibrated detection was
achieved.

The future calibrated fixture is not a renamed or reconstructed J1 fixture. It
must have its own identity and, before analysis, freeze at least:

- immutable raw dual-RX IQ geometry, byte range, size, and digest;
- radio, receiver, RF/IF, sample-rate, time, gain, and continuity provenance;
- an immutable per-receiver frequency-calibration authority and digest;
- predeclared search coverage, expected numerical metrics, and tolerances;
- positive role and independent null, stationary-interferer, wrong-pattern,
  and surrogate controls using the same search scope; and
- explicit boundaries between frequency calibration, candidate evidence,
  false-alarm/specificity calibration, attribution, and payload decoding.

The fixture can qualify calibrated frequency handling and reproducible
candidate behavior. A calibrated *detection* or specificity claim requires an
independently reviewed truth/negative corpus and false-alarm methodology; a
receiver frequency offset alone cannot supply that evidence.

This option allows completion to be judged against evidence that still exists,
while making the evidentiary loss and resulting claim boundary permanent and
machine-testable. Its cost is an explicit revision of the original acceptance
contract and loss of executable historical J1 comparison unless J1 is later
recovered.

## Claims forbidden under either option

Unless future evidence independently proves them, neither option permits a
report, UI, CLI, test, fixture state, or requirement status to claim or imply:

- recovery of the J1 full IQ object, selected IQ window, or frozen calibration;
- byte, epoch, CFO, QAM, track, or end-to-end parity on J1;
- a calibrated J1 detection or proof that current code finds the historical J1
  observation;
- detector specificity, a false-alarm rate, occupancy, or prevalence inferred
  from J1, RETRO, post-selected windows, or conditioned controls;
- phase/sample coherence between radios, decoded Starlink user payload, or
  attribution of a candidate to a particular satellite or transmitter; or
- equivalence between reports/plots/derived JSON and immutable raw evidence,
  or between a numerically similar mutable calibration and the missing frozen
  object.

Option A additionally forbids closing R-018 on RETRO alone. Option B permits
closing only a separately reviewed, rewritten R-018; it forbids describing
that closure as J1 recovery, J1 parity, or calibrated detection.

## Recovery and reacquisition triggers

The exact-byte J1 recovery trigger remains live under both options. Discovery
of a candidate object does not change status by itself. It starts a bounded
review that verifies the identities above, provenance, geometry, and
calibration before materialization or execution. A successful review adds a
new protected fixture revision and can propose restoring a J1 parity gate; it
does not rewrite old audit history.

A new calibrated capture triggers the separate future-fixture workflow. It
must never reuse the J1 fixture ID or J1 oracle values. Acquisition, fixture
truth, calibration authority, and thresholds must be frozen before using its
results to set acceptance tolerances. Failed or ambiguous reacquisition is
retained honestly as evidence but cannot be promoted by relabeling it.

## Migration and test implications

This decision causes no database, runtime, local fixture-payload, or QNAP
change. The corpus declaration advances additively from
`org.leo.test-corpus/v1` to `org.leo.test-corpus/v2`; v1 remains readable and
immutable, while v2 adds the non-executable
`UNAVAILABLE_HISTORICAL_EVIDENCE` state. The committed J1 declaration, plan,
inventory, and contract tests change atomically with this acceptance.

Had Option A been accepted, no plan migration would have been needed. Tests
would have continued to assert that J1 was explicitly `PLANNED` and never
silently skipped. Under either decision, a later recovery requires a reviewed
corpus-registry revision and protected fixture import; only after verified
materialization may a separate reviewed change convert it to a required
fail-closed parity lane. If the recovered calibration cannot be represented
without changing a published contract, introduce an additive contract version
and catalog migration rather than mutating v1 or back-processing historical
recordings automatically.

The accepted Option B change is atomic and reviewable:

- amend WP5, the detector gate, R-018 acceptance evidence, and any production
  gate dependency in `plan.md` without retroactively claiming the old gate
  passed;
- change the J1 corpus declaration from `PLANNED` to an explicit unavailable
  historical state, preserving all hashes and audit links;
- retain tests that fail if J1 is reported as present, executed, passed,
  calibrated, or silently omitted from the declared inventory;
- retain the exact protected RETRO input/oracle checks and end-to-end parity
  lane as required and fail-closed;
- add a distinct required gate for the future calibrated fixture only after
  its evidence package has been independently reviewed; and
- update presentation wording or contracts only if they cannot express the
  distinction between unavailable historical evidence, candidate parity, and
  calibrated qualification.

No PostgreSQL migration is needed because fixture requirements remain in the
file-backed corpus declaration, not the catalog. The contract change uses the
new corpus v2 major while retaining v1 readers. Any future catalog-persisted
fixture-state enum, calibration input, or presentation field must follow the
contract-first rules: additive evolution or a new major version, an Alembic
migration where catalog state changes, no mutation of published v1 values, and
no automatic reprocessing of old recordings.

## Adoption record

Option B was selected by the project owner on 2026-08-19 UTC. This accepted
ADR and its coordinated plan/corpus/test changes are one reviewed change set.
Any future J1 recovery or calibrated-fixture adoption requires a new reviewed
change; absence alone can never be promoted into scientific evidence.
