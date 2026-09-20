# Current positioning cohort: recorded timing bounds

Read-only inspection of the published manifests for all 211 recordings in the
recent 48-hour independent-search input finds first-sample UTC brackets of
199–252 ms. These brackets do not justify treating the fitted ±500 ms recording
clock corrections as measured clock errors.

| Rate | Recordings | Minimum bracket (ms) | Median bracket (ms) | Maximum bracket (ms) | Originally qualified |
|---|---:|---:|---:|---:|---:|
| 10 MS/s | 71 | 199.317 | 203.032 | 234.823 | 40 |
| 15 MS/s | 83 | 200.066 | 202.827 | 218.283 | 51 |
| 20 MS/s | 57 | 200.227 | 203.932 | 251.710 | 33 |

Medians use the middle ordered value (each cohort has an odd count). Maximum
realtime/monotonic offset spread is 0.005689 ms. Of the manifests, 87 preserve
an earlier 50 ms qualification threshold and are marked unqualified; 124 use
the later 2 s threshold and are qualified. Changing the threshold did not
make these brackets narrower. This is the original manifest status, not an
audit of the tracking service's later qualification policy.

The midpoint uncertainty implied by these brackets is approximately ±100–126 ms,
conditional on the host UTC clock and bracketing procedure being accurate. It
does not independently establish absolute UTC accuracy or rule out systematic
timestamp semantics errors.

The previous conditional position replay allowed ±500 ms per recording, with
108/211 clocks at a bound in the full cohort. Those bound values lie outside
every recorded midpoint bracket. Such fitted parameters can absorb orbit,
association, or measurement-model errors as well as timing error. Expanding
their bounds solely to reduce residual RMS would not establish better location
accuracy. No production timestamps or qualification policy were changed.

The independent wide-region search remains in progress. Its established fixed,
shared-clock, and recording-clock comparisons are retained for comparability;
the recording-clock model must be interpreted as a nuisance sensitivity model.
A subsequent physically constrained replay should use each recorded interval
and separately represent orbit uncertainty, rather than conflating the two.

The research replay now accepts `--timing-audit` on
`tools/replay_wide_session_clocks.py`. It binds numerical session groups to
recording identities through the frozen assignments, verifies their evidence
UTC references against the manifest estimates, and constrains each correction
to its recorded earliest/latest interval. Intervals outside the propagated
±0.5 s domain are rejected rather than extrapolated. The existing unconstrained
comparison remains available. This option has not changed production analysis.

Validation: the new constraint test first failed because the fitter did not
accept interval bounds, then passed after implementation. Five focused tests
cover physical position/clock recovery, fitting/evaluation isolation, constrained
clock estimates, invalid intervals, recording/reference mapping, and grouping.
The constrained recent-wide replay is pending the independent search result;
no position improvement is claimed from this implementation alone.

[Manifest timing fields and manifest digests](2026_09_20_track_position_information/capture-timing-audit.json)
were read through `AdaptiveHopIqStore.inspect`, without reading IQ or changing
stored recordings. [Conditional recording-clock results](2026_09_20_recording_clock_transfer.md)
document the fitting comparison.
