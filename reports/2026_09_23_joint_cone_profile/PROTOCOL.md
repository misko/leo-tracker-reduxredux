# Joint candidate and mounting-orientation profiling: TRAIN prototype

This is a new experiment, separate from the running fixed-candidate cone
cross-validation. No numerical results exist yet. Its purpose is to test whether
the shared mounting constraint resolves competing Doppler associations, not to
claim measured RF beam calibration or sub-300 m accuracy.

## Frozen first comparison

Use the same five unique geographic cells and the same twelve TRAIN scans as
the fixed-cone experiment. Keep every eligible track of at least three seconds
in the denominator. Use existing randomized RF training/evaluation masks.
Fit all per-track CFO offsets on training samples only. Do not open VAL/TEST or
reference coordinates. Freeze inference before any geographic-error evaluation.

At each location calculate candidate Doppler residuals and local sky directions
once. Start with the full causal catalogue and physically above-horizon
candidate support at that location. A candidate may be discarded only when its
training RF cost cannot beat the unassigned cost. Record catalogue completeness,
any additional candidate cuts, and failures; do not call a shortlist exhaustive.

For track i of duration w_i and candidate s, define the training RF cost
c_is = min((training_RMS_is / 800 Hz)^2, 1). The 800 Hz scale is the previously
requested diagnostic threshold; it is fixed here, not selected from truth.
Use one common orientation for both nominal axes, separated by 20 degrees,
throughout all twelve scans. Evaluate both provisional receiver mappings and
10, 15, 20, 30 degree cone half-angles separately; do not select width by location
error. Keep the initial tilt limit of 15 degrees as an explicit scenario.

At each orientation, a candidate is compatible only if its directions at all
available training observation times lie in the corresponding cone. This is a
sampled-support test, not a continuous-visibility proof. Choose each track's
lowest-cost compatible candidate, or assign cost one if none improves it.
Minimize sum(w_i * assigned_cost_i) / sum(w_i). Equivalently maximize the sum of
w_i * (1 - c_is) for the best compatible candidate of each track. Each track
contributes once. Keep unsupported tracks in the denominator and in outputs.
This hard-cone model is an explicit sensitivity experiment, not a production
exclusion rule for an uncalibrated antenna. Compare against identical Doppler-only
scoring with cone constraints removed.

Freeze orientation, mapping, and candidate assignments before evaluating held
RF rows; do not refit CFO or select an orientation from held RMS. Report total
eligible/support duration, tracks, observations, supported and unsupported
counts, training loss, held RMS of supported tracks, held capped loss with all
tracks retained, and sampled held-direction coverage. Report each width and
near-tied orientations rather than claiming a uniquely measured boresight.
Repeated observations/scans and uncertain identities are not independent trials.

## Search and safe pruning

Cache candidate RF costs and ENU directions per geographic cell. Cone rotations
need dot products, not new orbit propagation. Initially compare exact batched
enumeration with the accelerated result on the same finite orientation grid.

For a region of orientations, bound the angular movement of each receiver axis
from a representative by epsilon_RX. A candidate whose maximum sampled angular
distance from that representative exceeds width + epsilon_RX cannot fit
anywhere in the region (spherical triangle inequality). Among all remaining
candidates take each track's largest possible weighted improvement; their sum
is an optimistic regional upper bound. This deliberately permits different
orientations for different tracks, so it cannot underestimate achievable gain.
Prune only when that bound cannot improve the incumbent; retain equality when
enumerating tied solutions. For finite orientation groups, epsilon is computed
from their actual axes, not guessed from Euler parameter spacing. Any continuous
search requires its own certified rotation bound.

This bounds orientation search at one location only. Do not reuse it as a
geographic-cell bound: satellite directions and RF costs change with location.
Measured runtime, evaluated orientations, pruning, assignment parity, score
parity, and ties must accompany any speed claim.
