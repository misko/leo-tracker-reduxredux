# Closer-epoch retrospective TLEs substantially reduce the recent position bias

Replacing only the orbital elements reduces the selected fixed-clock position
error from **4,582.8 m to 1,132.3 m**. Satellite identities, RF observations,
randomized partitions, quality selection, and fitting procedure are unchanged.
This is the strongest explanatory lead from the recent audits, but **not yet
sub-kilometre accuracy and not a causal real-time result**.

## Selection independent of RF residuals and location

For each frozen satellite identity, choose the archived element epoch nearest
the recording start. Unlike the earlier causal audit, later publications and
later element epochs are permitted. Selection uses only epoch distance, then
collection time and digest as deterministic tie-breaks. It does not examine
signal residuals or the known antenna coordinate.

The read-only audit considered 176 available archive snapshots collected between
seven days before the earliest recording and seven days after the latest one.
The latter bound does not imply seven days of future data exist: only currently
archived snapshots were considered. All 622 assignments have an available
replacement; 560 selections were published after the corresponding capture.
The median original element age is 20.52 h; the median absolute selected epoch
distance is 3.30 h. Exact element texts, collection times, and digests are saved.

## Results

| Cohort | Clock model | Original error (m) | Closer-epoch error (m) | New evaluation RMS (Hz) |
|---|---|---:|---:|---:|
| All 622 tracks | Fixed recorded UTC | 4,800.8 | 1,202.6 | 794.15 |
| All 622 tracks | Shared ±0.5 s | 3,805.0 | 1,430.1 | 793.69 |
| Selected 190 tracks | Fixed recorded UTC | 4,582.8 | 1,132.3 | 86.15 |
| Selected 190 tracks | Shared ±0.5 s | 3,887.7 | 1,730.5 | 84.88 |

The selected fixed-clock evaluation RMS was 85.91 Hz before and is 86.15 Hz
after. Nearly unchanged short-track residual RMS accompanies a large change in
absolute position error. This illustrates why low Doppler residual alone cannot
establish absolute positioning accuracy when the orbits are uncertain.

The propagated satellite-state displacement has median **5,228 m** and maximum
**707,262 m** across all observation epochs. This is disagreement between TLE
solutions, not a measured satellite-position error. All replacements pass the
existing propagation validity checks, but that does not establish their accuracy.
The substantially worse all-cohort RMS shows that closer epoch is not uniformly
better for every original assignment; incorrect identities, manoeuvres, or bad
orbital solutions remain possible. The frozen selected cohort avoids that large
RMS increase without being reselected using the new result.

The fit still uses original causal catalogues for the preceding wide-region
search and original identities. Therefore this establishes **local orbit
sensitivity after independent wide acquisition**, not an independent global
search performed with the retrospective catalogues. The antenna coordinate is
used only after inference to compute the table's distances.

## What this changes

The results support orbit prediction uncertainty as a substantial contributor
to the shared bias. Earlier frame, channel, sample-rate, altitude, and capped-
observation audits produced much smaller improvements. They do not prove that
these retrospective TLEs are exact or that future-data access solves the full
problem. A practical device would need better causal orbit products, a justified
orbit-error model, or independent geometric constraints.

A useful next diagnostic is to compare the nearest preceding and succeeding
element epochs separately and assess whether their propagated disagreement
predicts the position sensitivity. No model or orbit should be chosen by its
distance from the antenna reference.

## Evidence and reproduction

`tools/audit_causal_tle_freshness.py --nearest-offline` enables this explicitly
non-causal selection; default causal selection is unchanged.
`tools/replay_wide_alternative_tles.py` validates parent digest, assignment order,
satellite identity, UTC, observation values, and randomized partitions before
replacing propagated states. Invalid propagation would retain the original
state and be logged; none occurred here.

Six focused tests pass, covering strict causal selection, explicit offline
nearest-epoch selection, rejection of non-causal updates by the existing causal
replay, and refusal of mismatched assignment order/identities. Existing physical
fitter tests remain the numerical basis for the unchanged fitting procedure.
No production timestamps, TLE policy, or scanner configuration changed.

- [Selected element texts, epochs and provenance](2026_09_20_offline_orbit_sensitivity/nearest-epoch-audit.json)
- [All fits and state-disagreement statistics](2026_09_20_offline_orbit_sensitivity/inference.json)

## Follow-up: preceding, succeeding, and interpolated epochs

The same archive audit now retains the nearest epoch on each side of recording
start. Preceding epochs exist for all 622 assignments; succeeding epochs exist
for 548. Median absolute distances are 8.31 h and 7.34 h respectively. This is
still an offline comparison: even a preceding epoch can have been published
after the capture. The causal default policy remains unchanged.

| Orbit policy | All fixed error (m) | All shared-clock error (m) | Selected fixed error (m) | Selected shared-clock error (m) |
|---|---:|---:|---:|---:|
| Original causal catalogues | 4,800.8 | 3,805.0 | 4,582.8 | 3,887.7 |
| Nearest epoch | 1,202.6 | 1,430.1 | 1,132.3 | 1,730.5 |
| Nearest preceding epoch | 2,261.7 | 2,191.9 | 2,483.1 | 3,329.0 |
| Nearest succeeding epoch | 1,483.9 | 1,318.2 | 1,322.3 | 1,501.3 |
| Interpolated bracketing epochs | 1,315.9 | 1,469.9 | 1,204.2 | 1,772.2 |

The succeeding-only run keeps the original state for the 74 assignments without
a succeeding epoch and records those fallbacks. The interpolation experiment
instead falls back to the nearest archived epoch when a complete nonzero-width
bracket is unavailable. No track is silently deleted. These fallback policies
are part of the experiment, not a claim of complete retrospective coverage.

For a complete bracket, both TLEs are propagated to each observation time. The
Earth-fixed positions are blended with the epoch-distance fraction, clamped
to [0,1]. Velocity includes the derivative of that weight:
`v = (1-w) v_before + w v_after + dw/dt (p_after-p_before)`.
A finite-difference test verifies that blended velocity matches the derivative
of blended position, including points outside the bracket. This is a smooth
local ephemeris sensitivity experiment, not a new orbit determination or a
dynamically constrained orbital solution. In particular, it need not represent
an actual manoeuvre between element epochs.

The selected fixed-clock evaluation RMS falls from 86.15 Hz for nearest epoch
to 79.1 Hz for interpolation, while position error rises from 1,132 to 1,204 m.
Again, residual reduction alone is insufficient to choose the most accurate
position. None of these alternatives is selected by its reference error or
promoted to production. Seven focused orbit-policy and interpolation tests pass.

- [Epoch brackets and unavailable successors](2026_09_20_offline_orbit_sensitivity/bracketing-epoch-audit.json)
- [Preceding-only fits](2026_09_20_offline_orbit_sensitivity/preceding-inference.json)
- [Succeeding-only fits](2026_09_20_offline_orbit_sensitivity/succeeding-inference.json)
- [Interpolated fits](2026_09_20_offline_orbit_sensitivity/interpolated-inference.json)

Reproduction uses `--epoch-side preceding`, `succeeding`, or `interpolated` on
`tools/replay_wide_alternative_tles.py` with the saved bracketing audit. All three
require explicit offline provenance. Model inputs remain frozen from the same
independent wide acquisition.

## Nearest-epoch orbits with recorded clock bounds

The next replay preserves all satellite identities and the original quality
selection. Each recording's measured first-sample UTC bracket constrains its
clock correction. The shared-clock variant uses the intersection of brackets
for the recordings actually present in that cohort. Neither inference nor
bound construction reads the evaluation coordinate.

| Cohort | Clock model | Horizontal error (m) | Random held-out RMS (Hz) |
|---|---|---:|---:|
| All | Fixed | 1202.56 | 794.15 |
| All | Shared, original ±0.5 s | 1430.05 | 793.69 |
| All | Shared, recorded bounds | 847.71 | 793.96 |
| All | Per recording, recorded bounds | 1169.06 | 792.70 |
| Selected | Fixed | 1132.29 | 86.15 |
| Selected | Shared, original ±0.5 s | 1730.46 | 84.88 |
| Selected | Shared, recorded bounds | 999.33 | 85.49 |
| Selected | Per recording, recorded bounds | 1254.08 | 82.09 |

Both shared recorded-bound fits hit a clock bound. The selected result is only
0.67 m inside 1 km, insufficient margin for a verified sub-kilometre claim.
Exact orbit propagation at the fitted clock, numerical convergence and
group-deletion stability remain to be checked. The all-track result also has
large residuals, so its lower position error does not establish a better model.
These remain retrospective orbit replays, including elements published after
capture, rather than a demonstrated real-time device solution.

Four focused tests pass, including subset-specific intersection, incompatible
bounds and missing group rejection. Reproduce the nearest-epoch command with
`--timing-audit reports/2026_09_20_track_position_information/capture-timing-audit.json`.

[Inference and recorded input digests](2026_09_20_offline_orbit_sensitivity/recorded-clock-inference.json)
