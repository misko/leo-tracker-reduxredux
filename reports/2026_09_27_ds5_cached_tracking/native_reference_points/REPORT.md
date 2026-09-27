# Native scoring at missed reference hypotheses

The complete two-candidate replay left twelve application-relative receiver
identity losses. None had a matching pair in the full positive native candidate
inventory. This diagnostic tests the final raw native point statistic with
oracle-supplied reference coordinates, separating it from blind search.

The fixed inventory contains all twelve lost receiver rows plus four matched
anchors, 21 selected pairs and 42 coordinates. Each row includes its strongest
application pair and, where different, its strongest pair with both acquired
and physical CFO within +/-400 kHz. The extra five pairs are frequency-alias
contrasts, not a new requirement that physical CFO stay below 400 kHz.

## Results

The current Python scorer reproduced all 42 original candidate scores and
frequencies within the frozen tolerances. All 21 reference pairs passed.
The native guided assessment passed 19/21 pairs: all four anchors, 15/17 pairs
from lost receivers, and the strongest selected pair for 11/12 lost receivers.

This demonstrates that supplied hypotheses can recover raw native point
evidence for most missed receivers. It does not demonstrate a causal way to
find those hypotheses or equivalence with tone-conditioned blind scoring.
Timing and expected physical CFO were supplied by the reference here; no
independent timing fit or blind hypothesis generation was performed.

Two distinct failures remain:

- At 2.5 MS/s visit 1104 RX1, the strongest pair's first point has scoring CFO
  320268.11034612823 Hz and expected physical CFO 206631.74670976176 Hz. Their
  difference exceeds `0.5 / 4.4e-6` by approximately 2.8e-9 Hz. The runner's
  support precheck did not call the native API for this point. This is a
  numerical admission-boundary issue, not an observed low GLRT score.
- At 5 MS/s visit 1094 RX0, the within-400-kHz contrast fails physical-frequency
  association: the native point reports roughly -474.2 kHz instead of -247.4 kHz,
  an approximately 226.8 kHz alias difference. Its status rejects the innovation.
  The strongest pair for this receiver passes. This is distinct from the
  nanohertz admission issue and must not be hidden with a wider identity gate.

The original runner therefore made 42 Python calls and 41 actual native calls,
with one explicit support-precheck outcome. A subsequent immutable
`boundary_api_audit.json` directly called the unchanged native API at that
original coordinate: it returned no observation. One `nextafter` step of the
expected physical CFO toward scoring CFO (+2.91e-11 Hz) still returned none.
This is supplemental post-outcome evidence, not a rewrite of the frozen receipt
or a repair of the kernel. The original prescribed per-coordinate call count
was not met for that one point during the primary run.

All strongest application pairs have acquired/scoring CFO within +/-400 kHz,
including pairs whose residual-corrected physical frequency exceeds 400 kHz.
Physical CFO alone is not evidence that the acquisition hypothesis lies outside
the native input range. V3 evaluates innovation against expected physical CFO.

## Next implementation choices

The leading path is a bounded same-receiver rescue acquisition followed by
fresh confirmation, rather than simply doubling native candidate count again.
`RESCUE_FEASIBILITY.md` records the current evidence and cost model. Its cost and
accuracy have not yet been measured. Separately, an explicit microhertz-scale
input-support tolerance can address the numerical admission issue while
preserving the measured 8 kHz innovation gate and the supplied frequency values.

The primary diagnostic completed in 0.53 seconds, with immutable inputs and
stable frozen sources. Individual point timings are not detector speedups:
search is omitted and hypotheses are oracle-supplied. All data is development
data; validation IQ remains ungenerated and the original holdout unopened.
