# Curvature check after paired fitting

Before geographic scoring, verify the original fit seal and evaluate each
returned slope arm at its selected fitted point, without refitting or changing
selection. Apply the preceding identifiability calculation's main/half Hessian
steps and diagnostics to all eight records. Preserve missing/unqualified fits
and record any timing-knot crossing, visibility change, nonpositive block or
step/asymmetry warning. Do not use a curvature result to select another start.

This supplementary calculation addresses curvature at fitted points rather
than the earlier full88 expansion points. It does not tune the model and never
loads roof reference coordinates. All outputs remain diagnostic, including
failed numerical checks. One sequential batch is capped at 180 seconds and
4 GiB, one numerical thread and nice19; no retries or corpus mutation.
