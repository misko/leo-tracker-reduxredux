# Pilot corrections improve pair agreement but leave shared residual structure

The influential conditional-source tracks in scans0 and16 share substantial
residual structure. Long-pilot corrections with the frozen reliability fallback
reduce differences between paired measurements, while most common residual
structure remains. This helps explain why improved waveform measurements need
not produce consistent geographic gains; it does not identify the common
error's physical cause.

Both measurement arms are evaluated at the same original IID endpoint in each
scan. Each track's constant CFO is profiled on its original training mask.
Mutual nearest training timestamps must be within0.25seconds. No new position
fit, held observation, reference coordinate, IQ read or orbit update is used.

| Pair population | Measurement arm | Pearson correlation | Common-component RMS | Differential-component RMS | Centered pair-difference RMS |
|---|---|---:|---:|---:|---:|
|Scan0:12 cross-band pairs, RX0|GLRT|0.942|135.01Hz|24.43Hz|50.28Hz|
|Scan0:same pairs|Long pilot|0.962|135.47Hz|20.19Hz|37.73Hz|
|Scan16:42 simultaneous cross-RX pairs|GLRT|0.957|256.56Hz|66.23Hz|133.83Hz|
|Scan16:same pairs|Long pilot|0.976|245.77Hz|45.44Hz|88.45Hz|

Common and differential components are half the sum and half the difference
after centering each paired sequence by its own median. The last column instead
centers the differences themselves; medians need not commute, so it is not
exactly twice the preceding column. All frequencies are canonical11.2GHz Hz.

Scan0 compares10.71GHz and11.21GHz tracks conditionally assigned to NORAD65512.
The12 paired samples are sequential visits, separated by at most0.14126seconds.
Their modeled Doppler differences are explicitly retained; the raw measurement
differences must not be treated as simultaneous-frequency errors. Scan16's
42 pairs observe11.46GHz on RX1 and RX0, conditionally assigned to NORAD67103.
All42 share a visit and original timestamps differ by at most39nanoseconds.
The centered predicted pair difference is below0.00005Hz under either arm.
The third scan16 track has no qualifying overlap with either of the others;
both zero-match comparisons remain in the results.

Rank-based checks agree with the correlation result: Spearman values rise
0.909→0.965 on scan0 and0.910→0.947 on scan16. The scan16 median absolute
common component remains174.41→178.01Hz, whereas its differential component
changes25.02→22.05Hz. The finding therefore is not supported only by RMS and
one extreme pair. These small, dependent pair populations are not independent
validation trials, and matching does not establish signal identity.

This is DS11 evidence for a pattern previously observed in DS7–9:
[candidate-specific slope transfer](../../2026_09_29_candidate_rx_transfer/README.md)
and [curvature transfer](../../2026_09_29_curvature_transfer/README.md) improved
held residual prediction across receivers without establishing orbit corrections.
Earlier [differential-drift geographic tests](../../2026_09_29_drift_geographic/README.md)
completed54 arm/panel combinations without reliable sub-km improvements.
Those existing results argue against simply repeating receiver-drift allocations
or subtracting the newly observed shared residual.

The shared structure can include receiver-position error itself, orbit error,
clock/timing error, transmitter behavior, shared extraction artifacts, or
incorrect conditional associations. Removing it with an unrestricted slope or
curvature would risk removing position information. This diagnostic cannot
separate those causes or justify changing a satellite assignment.

Two component tests cover unique bounded matching, tie handling, constant-offset
invariance, and common/differential decomposition. Both bounded runs exit0.
The [verification](verification.json) rehashes source bindings, checks pair
uniqueness and time bounds, independently reproduces centered differences,
and records the rank statistics. Full paired rows are retained in
[scan0](00.json) and [scan16](16.json), with the [protocol](PROTOCOL.md).

The next modeling priority remains the distinction between competing GLRT
interpretations of the same acquisition and independent observations. The
existing greedy overlap selector and simple source balancing did not establish
a general gain. Before another position fit, an alternative-hypothesis model
needs a common observed-data support and a normalized likelihood that accounts
for measurements not explained by each hypothesis. The pair agreement found
here must not be used to assume independent evidence or authenticated identity.
