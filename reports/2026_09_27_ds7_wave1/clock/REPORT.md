# DS7 direction C receiver-clock gate

Status: **not admitted; no DS7 clock fit was attempted**.

The initially considered constant receiver-frequency bias is rejected as
structurally redundant. The baseline already fits an independent offset for
each track. For either receiver, its constant indicator is exactly the sum of
the offset indicators for tracks on that receiver. A calibration prior could
choose a decomposition between those terms, but it would add no observation
geometry.

The frozen next candidate is one receiver-shared linear frequency drift in Hz/s,
applied to time centered within each track while retaining the baseline
per-track offsets. Sharing across captures is prohibited unless independent
evidence establishes stable physical-path and hardware-epoch identity.
Zero-drift replay is the required control.

Sample-clock ppm, UTC bias/drift, and an LNB state remain excluded. The allowed
inputs contain nominal sample rates and host capture-time bounds, but no
independent sample-rate reference, device-counter calibration, UTC authority,
LNB calibration, or receiver drift bound. Across the 88 public plan rows, host
start brackets are approximately 362–369 ms wide. Repository acquisition code
treats a host read bracket as a refill timestamp rather than a device-sample
timestamp. Nominal sample count divided by nominal sample rate is circular
evidence for sample-clock error.

## Evidence audited

- The reference-free budgets plan contains 88 captures from radio_pluto_5d4d,
  always receivers 0 and 1, at nominal rates 2.5, 5, 7.5, or 10 MS/s.
- The available baseline export is identity-bound to the first capture and has
  56 public tracks and 2,391 observations with receiver IDs, channels, RF
  centers, relative times, measured frequencies, visits, and train masks.
- That export declares candidate_policy_state = not_exported. It contains no
  candidate bank, orbit model, fitted residual, or position/nuisance Jacobian.
- No independently evidenced receiver/sample-clock drift or stability bound was
  supplied in the allowed inputs.

## Structural projection

Using the real track membership, the 56 per-track offset columns plus one
constant receiver column have rank 56/57. After projecting on track offsets,
the receiver-constant normalized norms are 7.84e-16 for receiver 0 and 5.52e-16
for receiver 1. The constant extension is therefore rejected regardless of
calibration identity or prior width.

A track-centered receiver linear-drift column survives this limited projection:
both receiver designs have rank 57/57 and projected norm 1.0. This establishes
only independence from per-track constants. It does not establish independence
from position or other nuisance derivatives, which cannot be tested until the
matched baseline Jacobian is available.

## Gate decision

The drift candidate fails admission because matched candidate/orbit/residual
and Jacobian products are absent, and because no independently derived physical
drift constraint is available. Fitting now would let an unconstrained slope
compete with an unmeasured position derivative.

The frozen thresholds are in [frozen-config.json](frozen-config.json), and the
machine-readable failures are in [gate-status.json](gate-status.json). The
unregularized scaled design must have full rank and condition number at most
1,000, while each clock column must retain at least 0.05 of its normalized norm
after projection on position and existing nuisance columns. Zero and both
independently bounded drift endpoints must be recovered within the larger of
0.05 Hz/s or 10% of the allowed interval width. Constraint removal must not
change rank, produce a boundary solution, or move the estimate by more than two
standard errors.

The pure numerical check also accepts an independent synthetic column with
exact recovery of 0 and ±250 injected units, and rejects an exactly confounded
column. [synthetic-check.json](synthetic-check.json) records both that check and
the real membership projection. These checks do not establish full DS7
identifiability or calibration.

## Required handoff before fitting

Direction A must seal the matched candidate bank and orbit inputs together with
per-observation residuals and the position/existing-nuisance Jacobian for the
same frozen panel. Each observation must retain receiver_id. The coordinator
must also supply separately derived, evidence-backed receiver drift bounds
valid over each fitted capture, plus stable path/epoch evidence before allowing
cross-capture sharing. Only then can direction C run zero replay,
injected-error recovery, constraint-removal, and held-group location gates.

No pose, reference coordinate, full DS7 manifest, or scored output was read.
