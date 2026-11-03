# Receiver calibration preparation

Use only the two metadata-compatible DS10 numerical exports from the sealed
inventory, in chronological order. They precede both DS11 pilots and match
5MS/s, exact RF centers and radio. First recording is calibration, second is
validation. This is conditional development evidence, not an authenticated
identity or independently surveyed beam calibration.

Use original DS10 training-fitted geometry (the existing pooled DS10 fit) only
as a fixed geometry input; no DS11 coordinate or reference error enters. This
geometry uses training data from both recordings and other earlier DS10 captures,
so validation is conditional on that Doppler geometry, not a blind pipeline test.
Retain the original visit masks. Select physical candidate labels from each
track's training-only IID posterior at that geometry with the previously used
0.90 confidence threshold. Ambiguous tracks remain explicitly unassigned.

Reconstruct source track point IDs through public ports. Group confident tracks
by physical catalogue identity and exact RF. Record all paired opportunities
over the full scan, not only the interval bracketed by source detections. Build
source-specific receiver bits from track memberships. Unknown receiver support
must remain unknown. Shared raw candidates assigned to different candidate
identities make those source/receiver bits unknown; never duplicate a confirmed
positive. Distinguish these inferred source-track labels from verified emitter
truth and from raw probe nonemptiness.

Reconstruct exactly the original newest-per-object causal catalogue using
provider/digest/collection-time bindings. Repropagate selected candidate states
at original track times and timing nodes to verify bank parity before computing
candidate LOS on the complete probe grid. No later orbit records are used.
Keep all groups/empty opportunities and report unknown/ambiguous support counts.
Each donor export gets a 90-second single-thread cap. No geographic fit yet.
