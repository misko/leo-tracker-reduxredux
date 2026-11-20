# Diagnose the frozen no-intersection outcome

Run this diagnostic only after the original prediction seal and before reading geographic scoring. Keep the same six inputs, link, causal catalogue, four retained orbit options per arc and phase prior. Preserve all original predictions and gates.

Count candidate pairs after removing same-block and same-NORAD pairs, after the 0.45 angle test, and after the 35 km conditioning floor. Report the nearest linear line-intersection conditioning among all angle-eligible pairs and among those whose coordinates geometrically lie inside the generic ±12.5 km box, even when they fail the conditioning gate. Do not emit any rejected intersection as a position.

Using the same retained causal candidates and sample times, measure the leading line strength after eliminating a per-arc constant or a per-arc affine frequency clock. The offset-only comparison is conditional on the same candidates and shows the cost of allowing an unknown slope. It does not assert the real receiver satisfies constant-offset-only behavior.

Measure train-selected, held-prefix-frozen late residuals at the supplied centre and its generic ±8 km east reflection. These three points are fixed in advance and only instrument the RF stage. They do not supply a position or change held association/phase controls. Maintain one distinct provisional NORAD per pass block and exclude trained NORADs from held.
