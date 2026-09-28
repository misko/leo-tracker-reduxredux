# Independent review: frozen residual trajectories

## Source review

The implementation is descriptive and does not fit a frequency correction, alias integer, slope,
nominee, or role-specific transformation. It exports every retained track-candidate component and
normalizes their saved training log priors after excluding `other`. Empty receiver observations
produce a missing nearest residual and remain in role denominators; invisible forecasts contribute
zero to the two alignment fractions.

Signed residuals use observed minus forecast on the lane's fixed half-open alias circle. The
nearest candidate minimizes absolute wrapped residual, with saved candidate index as the explicit
tie breaker. Each export preserves candidate index/ID/rank/margin, forecast, visibility, window ID,
role and timestamp. Adjacent changes are circular differences between consecutive saved windows.
They may join different nearest candidates and therefore are not physical Doppler derivatives.

The exact boundary export uses the final reception and first held-frequency window, after requiring
strictly increasing timestamps, both roles, and all reception windows before held windows. No
continuity condition is imposed. Per-role fractions use every window; signed and absolute medians
are conditional on a nonempty candidate set and remain descriptive on the selected circular branch.

The finalized production gate must require all six calibration recordings and all twelve lanes,
exactly one terminal `other` component with only track candidates before it, unique nominee pair
keys, both ordered roles per lane, and globally unique source windows. The launcher binds the
dataset and the preceding alignment evidence and runs with a 120-second, 4 GiB, single-thread
bound. Focused tests cover wrapping, saved-order ties, empty receivers, invisible forecasts,
role denominators, exact boundary extraction, prior normalization and input immutability.

The separate [provenance audit](PROVENANCE.md) finds no role-specific mapping discontinuity. It
also explains why the exported nearest-candidate sequence cannot identify a satellite or establish
a handoff. Outcome interpretation must retain that limit.

## Outcome audit

The run completed with exit code 0 and 123,900 KiB peak resident memory. It exports all six
calibration recordings, 12 lanes, 2,719 unique source windows, 54 nominees, and both receivers for
each nominee. The independent reconstruction audit passes all 108 nominee/receiver series and 108
exact boundary records. It recomputes saved-order periodic nearest selection, empty observations,
adjacent forecast/time changes, boundary identities, role denominators, alignment fractions, and
conditional medians directly from the frozen geometry dataset. The audit binds results digest
`3df3785b21a2ea3abe684d67769032f121ab4a12f5c90567f7cf78c6301a4c93`.

Exact-boundary residual changes are available for only 21 of 54 nominee series on RX0 and 15 of 54
on RX1; other series lack a candidate on one side. That missingness is itself consistent with the
documented reduction in detector support, but it prevents a general boundary-continuity statement.
Adjacent and boundary residual steps also use independently selected nearest candidates, so even a
small step would not prove persistence and a large step would not prove handoff or forecast drift.

The artifact is suitable for inspecting individual frozen residual paths and candidate-selection
changes. It supplies no basis to refit a slope, choose a best nominee from later outcomes, or assign
satellite identity. Any next aggregate should preserve empty boundary pairs and separate candidate
availability from residual magnitude rather than conditioning the headline result only on pairs
with observations on both sides.

The two README examples were selected after result inspection and are correctly labeled as
illustrations rather than validation. I checked their quoted boundary gaps, residuals, circular
candidate and forecast steps, held-window fractions, and 55.23/59.92/64.39-second snapshots
against the frozen rows. They agree after displayed rounding. The `9d7b6a...` example now includes
the full track ID needed to distinguish it from the second retained track with the same catalogue
number and a different fitted CFO.
