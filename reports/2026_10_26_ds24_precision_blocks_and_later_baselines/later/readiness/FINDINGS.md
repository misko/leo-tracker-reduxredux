# Four inputs are ready; preparation and geographic validation remain separate

All four previously selected recordings pass full public input-contract and
manifest/index authority validation, with no substitutions. The completed
metadata processing used **13.850 seconds**, including a conservative three-second
inspection allowance, below the 30-second cap. No IQ payload was opened, detector
was rerun, scientific input was prepared, position was fitted or GPS/error was
read. Root subsequently requested a review pause; numerical preparation has
not started.

| Label | Original recording ID | Acquisition UTC midpoint | UTC half-width | Raw windows | Valid receiver probes | Existing excluded windows |
|---|---|---|---:|---:|---:|---:|
| LATER4-0001 | `fast8-auto-20261024-224359-7249fa17-1-upper` | Oct 24 22:44:05.474481 | 0.088152 s | 6768 | 13536 | 0 |
| LATER4-0002 | `fast8-auto-20261024-233414-efe03d6d-1-lower` | Oct 24 23:34:20.940237 | 0.088353 s | 6764 | 13522 | 3 |
| LATER4-0003 | `fast8-auto-20261025-002429-895cc487-1-upper` | Oct 25 00:24:35.349182 | 0.088291 s | 6772 | 13530 | 7 |
| LATER4-0004 | `fast8-auto-20261025-020456-a88a5971-1-upper` | Oct 25 02:05:03.087350 | 0.089353 s | 6770 | 13518 | 11 |

Every case is qualified 10 MS/s fast input with two receivers and channels 1–8.
The excluded windows are existing invalid-capture declarations, not new
filtering. All other windows have exact receiver/probe coverage. Candidate
records, complete input hashes, raw source identity, declared analysis-manifest
identity and all segment/index bindings remain in the four detailed receipts:
[0001](LATER4-0001_validation.json), [0002](LATER4-0002_validation.json),
[0003](LATER4-0003_validation.json), [0004](LATER4-0004_validation.json).

## Authority checked

The public `FastScanStore` binds each exact recording/session/current run to its
tracking path. Isolated deployed `TrackingInput` validation checks the full
tracking contract; current public native manifest/index contracts check all
ordered window identities and support. The source inventory canonical digest,
ordered IQ-hash raw authority, original exclusions, counters, candidate fields,
margin flags and complete tracking-document rehash all agree. Reconstructed
raw authority matches each frozen previous declaration. This validates input
and metadata authority, not the underlying IQ bytes or detector correctness.

The actual fast preparation adapter uses the original `clock_anchor` host
before/after bracket. Its midpoint is the acquisition anchor and its BEFORE
bound is the causal TLE cutoff. This bracket—not filename time or segment
manifest creation—is now explicit in each sample member. Raw
`source.capture_start_utc_ns` remains null in these contracts; it was not
silently filled or confused with artifact creation. The existing bracket and
clock-step guards pass, and all lower bounds follow the original exclusive
cutoff. These are recorded host-clock authorities, not independent UTC
calibration claims.

No station, deployment, pose, mount or setup identifier was present in the
checked capture configurations. Radio/configuration digests do not prove the
evaluation site. **Evaluation truth is unknown from this evidence.** RF-only
preparation can proceed later under authorization, but a geographic accuracy
claim requires applicable independent truth and a declared evaluation-only
scope; no site coordinate should be supplied to inference on this basis.

Exact future historical-detector runtime/policy compatibility has not been
queried. Qualified 10 MS/s input and a declared analysis-manifest hash alone
do not establish compatibility with the earlier refiner runtime. Any later
measurement stage must separately bind the persisted execution policy,
code/environment, scope/symbol/grid conventions and exact replay parity.

## Handoff and hold

[prepared/sample.json](../prepared/sample.json) has four exact members,
`prepare_algo02_ds23.py`-compatible fields and SHA256
`c19af75560ff1ff962ec73064c49b68d10fe94bd990b37b09f73e588242e8ec5`.
[summary.json](summary.json) and [validation_result.json](validation_result.json)
bind the sources and full metadata result. The owned manifest checks have been
written but not run during the review hold. There is no frozen scientific
preparation protocol or launch receipt yet.

The intended existing entry point is
`tools/prepare_algo02_ds23.py --run-dir prepared --case LATER4-0001 --stage all`.
It exports the exact existing GLRT contract and constructs graph, nominal noise,
causal current/previous TLE banks and phase history. It does not construct a
retained optimizer parent by itself. Any future launch needs B preflight and
root GO, all four preserved slots, two BLAS1 workers, the original cumulative
600-worker-second ceiling including metadata, and at most 140 seconds per
case without retry or substitution. No such command was run here.

The panel can test a prospectively frozen correction policy on additional
existing recordings, with matched c arms and all failures retained. It cannot
by itself establish a clean holdout, true CFO bias, a calibrated uncertainty
model, full-DS23 improvement or operational promotion. Production inference was
already completed, geographic exposure remains incompletely audited, and the
previous exact-ID report search timed out. The four were not selected by
errors, and no new outcomes have been used to alter them.
