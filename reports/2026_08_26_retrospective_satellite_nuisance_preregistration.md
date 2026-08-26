# Retrospective Starlink association and receiver-nuisance preregistration

Date: 2026-08-26 UTC

## Frozen question

Can calibrated single-frame CFO measurements and a lean receiver-nuisance model
recover more catalog-ranked tracks or secure more NORAD identities than the
existing fixed-time, free-offset TLE comparison, without letting receiver
parameters absorb the satellite-specific Doppler shape?

The executable authority is
[`retrospective-satellite-nuisance-protocol-v1.json`](../config/analysis/retrospective-satellite-nuisance-protocol-v1.json).
This report records its intended interpretation before any new catalog-wide
candidate evaluation.

## Data boundary

The experiment is restricted to four exact, already-opened, counter-authoritative
POST-FIX captures from the existing `multi_radio`, `rate_development`, and
`v3_v4_canary` policy roles. It excludes every `holdout_foundation` response,
the polynomial hard-null backgrounds except as possible nulls, all PRE-FIX
captures, 3/5-MS/s capture-only data, unlisted/newer recordings, and dynamic
capture discovery.

Three primary capture tracks use the digest-frozen multi-radio frame ledger.
The 150802 primary track uses the existing 13.8 s, 550-row direct-GLRT ledger;
its 1.5 s multi-radio episode is a within-capture diagnostic and cannot create
an independent recurrence. All inputs were previously opened, so the result is
retrospective development evidence rather than a fresh acquisition holdout.

## Candidate population and TLE provenance

For each capture the protocol binds an exact, locally archived Space-Track
Starlink snapshot whose retrieval time strictly precedes the first measurement.
The candidate population is every SGP4-usable, altitude-plausible Starlink above
the geometric horizon at any actual measurement time. Membership is fixed at
the exact receive UTC before any nuisance or time-sensitivity calculation.

The search is catalog-wide only within the archived Starlink payload. It is
not an all-satellite or all-emitter search. Geometry is conditional on the
reviewed `spinnaker-sausalito` site preset because capture-bound position and
antenna boresight are unavailable.

## Frozen models

The current-method baseline fits one constant CFO offset per path at exact UTC:

\[
y_p(t)=D_j(t)+b_p+\epsilon.
\]

The primary nuisance model adds one regularized rate departure per physical
radio, shared by that radio's paths:

\[
y_p(t)=D_j(t)+b_p+\delta_{r(p)}(t-t_0)+\epsilon,
\qquad \delta_r\sim N(0,50^2\ {\rm Hz^2/s^2}),
\]

with a hard `+/-150 Hz/s` boundary. There is no candidate-specific free slope,
curvature, scale, or unconstrained time shift. A `+/-0.25 s` common time grid is
a sensitivity diagnostic; it does not choose the primary identity.

Measurements are reduced to per-path 20 ms UTC-bin medians and models use equal
path MSE so a dense path cannot dominate. Multi-radio identity/nuisance fitting
uses first-60% even-Qin measurements; final-40% odd-Qin measurements on the
same even-selected mask supply the response. The long 150802 branch uses a
chronological 60/40 split but remains hindsight-branch conditioned.

## Controls and promotion

Every winner is compared with:

- fixed-time free-offset TLE fits;
- shared linear and quadratic radio-only nulls;
- an over-flexible affine diagnostic;
- the ten neighboring catalog candidates;
- three rolling-origin fits;
- a bounded common-clock sensitivity grid;
- forty full-catalog wrong-time fields, giving a minimum matched-field p-value
  of `1/41`; and
- twenty within-path time permutations, giving a minimum p-value of `1/21`.

A recovered track and a secure NORAD are counted separately. Support plus a
finite full-catalog ranking can recover a track. A secure identity additionally
needs `<=100 Hz` held-out RMS, at least `20 Hz` advantage over the quadratic
null, strong training and held-out runner margins, nuisance and rolling-origin
winner stability, interior bounded-time behavior, both empirical controls at
`p<=0.05`, and recurrence of the same passing NORAD in at least two independent
capture IDs. A lower in-sample RMS alone can never increase either secure count.

## Frozen expected outputs

The bounded runner will emit a capture ledger, full candidate rankings, null and
control summaries, recurrence ledger, machine-readable evidence, an artifact
manifest, and plain Matplotlib PNGs. The report must state both baseline and
primary recovered-track counts and the complete secure-NORAD count, including
zero if the gates fail.
