# Pilot search interior does not establish frequency reliability

All124 scan16 excerpts completed this fitting-symbol-only audit in23.03seconds.
Every full estimate reproduces the original measurement exactly. Separately
fitting alternating four-frame groups exposes large instability in the two
excerpts that blocked the original short-arm replication. Their long-arm
full estimates were inside the search window, so the earlier boundary check
alone would not have detected this weakness in the long estimator.

| Native-frequency diagnostic | Short pilot | Long pilot |
|---|---:|---:|
|Median alternating-group disagreement|83.257Hz|18.097Hz|
|P90 disagreement|289.665Hz|55.544Hz|
|Maximum disagreement|3000.000Hz|1918.190Hz|
|Rows with either group at a search boundary|2/124|1/124|
|Median fitting-symbol coherent energy fraction|0.09127|0.08604|

At visit1308, RX1's long estimates from the two groups are-896.50Hz and
+1021.69Hz, disagreeing by1918.19Hz. RX0 gives-314.82Hz and-1500.00Hz,
disagreeing by1185.18Hz. Their long-arm coherent energy fractions are0.00655
and0.00568, compared with the all-row median0.08604. Short-arm disagreements
are3000Hz and1985.61Hz. These are descriptive diagnostics: frequency error
bars, false-alarm rates and signal identity are not established. Coherence
fractions from different window lengths are not directly calibrated tests.

The fitting windows alone supply these diagnostics. Waveform-held symbols,
localization-held IQ and geographic errors do not enter them. All observations
are retained. No threshold, correction blend, frequency-search expansion,
orbit update, position fit or promotion is performed. The original scan16
two-arm replication remains unavailable rather than becoming a successful
replication through a relaxed gate.

The next positioning experiment should distinguish reliable pilot corrections
from unstable estimates while preserving original GLRT observations as an
explicit fallback. Freeze its reliability rule before fitting positions, derive
that rule from fitting-symbol evidence rather than reference errors, retain
every row, and report how often each measurement source supplies the result.
Test both scan0 and scan16 so that a rule improving one does not erase the
other's evidence. A fallback gate is an estimator change requiring its own
validation, not a retrospective repair of the failed replication.

The [source-verified summary](summary.json), [full outcome](outcome.json),
[protocol](PROTOCOL.md), per-row records and process receipt preserve the result.
A synthetic test verifies tone recovery, instability across alternating groups,
and invariance to changes in held symbols. Full-data replay is exact for both
arms on all124 observations. The original attempt in `../pilot_reliability16/`
failed before any excerpt was read because a digest helper received a string
instead of a Path; all124 rows were not attempted. This separate revision binds
that failure and fixes only the argument types. Its single worker exits0 with
no failed, retried or unavailable rows.

Plan SHA256:
`4825d3ab3313f96a0ed99911ec86e7690249cb2d805541be8a55664724d46e50`.
