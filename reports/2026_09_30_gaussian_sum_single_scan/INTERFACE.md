# Gaussian sum single scan research interface

Revision 1, frozen before prototype implementation. This is a private research
boundary, not a published persisted contract. Coordinator owns this document.

The approved execution plan is `plans/gaussian-mixture-single-scan-localization.md`.
Three SOL workers share this checkout with disjoint ownership. Use the installed
`.venv/bin/python`, one numerical thread, and bounded jobs. Never mutate existing
dataset authorities, QNAP, golden fixtures or unrelated changes. No RF or raw-IQ
reprocessing. No nested agents.

## Ownership

- A: `evidence.py`, `test_evidence.py`, `selection.json`, `inventory.json`,
  `evidence/` beneath this directory. Freeze the selected 8/8/32 sessions before
  scientific evaluation. Audit pre-association observations and regional candidate
  completeness before deciding whether existing banks are reusable.
- B: `src/leo/analysis/gaussian_sum_location.py` and
  `tests/analysis/test_gaussian_sum_location.py`. Pure numerical implementation.
- C: `oracle.py`, `test_oracle.py`, `test_independent.py`, `oracle-results.json`
  beneath this directory. Independent equations/tests; no import of B's private
  algebra. Coordinate publicly callable API details with B.
- Coordinator: protocol, integration adapter/runner, evaluator, plots, receipts,
  gate decisions and final report. Request interface amendments through messages.

## Numerical boundary

B exports immutable Gaussian components (weight, mean vector, covariance,
identity history), a configurable bounded mixture, and a deterministic update
for one new observation factor. State dimension is generic; the real adapter
will supply regional ENU position and any explicitly shared nuisance states.

One factor contains physical observation IDs, observed vector, normalized source
priors including a background alternative, and candidate prediction callbacks.
For each candidate and supplied state, a callback returns predicted observations,
Jacobian and positive-definite noise covariance, plus eligibility. Signal and
background use identical observed dimensions. Priors may depend on state; initial
implementation must expose its local-constant approximation and a callback
mechanism or validation flag rather than silently asserting global validity.

Predictive evidence is calculated before assimilation, globally normalized over
all parent/candidate children. A location-independent background likelihood may
leave a component unchanged. Linear Gaussian track-local offsets can be included
by adding their proper prior covariance to measurement covariance. Persistent
nuisance variables belong in the state and retain cross-covariance.

Outputs include the posterior mixture, total predictive log density, association
probabilities, background probability, pre-normalization retained/discarded mass,
consumed observation IDs and deterministic status/flags. Greedy mode uses the
identical likelihood but retains one best child. Empty, duplicate, invalid or
over-budget factors must fail explicitly. Never conflate likelihood density with
a posterior probability or a Gaussian component contour with total credible area.

First prove exact small linear examples. Do not start real-data tuning while the
source/candidate audit or independent numerical gate remains unresolved. A shared
physical-error model and supported geographic prior are real-data integration
requirements, not something a generic filter API can establish by itself.

## Initial execution limits

Maximum three SOL workers and two numerical processes total, one numerical thread
each. A owns the single bulk-reader lease; B and C each have one short synthetic
numerical lease. Before a real fit the coordinator reallocates those leases.
Exports: 180 seconds each. Real fit: 90 seconds including load. Real-data batch:
at most eight scans and 15 minutes including prerequisites. No unattended corpus
campaign. Memory bounds and precise numerical thresholds are frozen in PROTOCOL
after input inventory and synthetic checks, before real scientific scoring.
