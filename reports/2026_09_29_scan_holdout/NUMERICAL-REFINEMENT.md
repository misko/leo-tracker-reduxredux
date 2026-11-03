# Timing integration refinement

During the frozen run, the DS7 late reverse baseline passed optimization but one
target timing integral differed by0.017906 between16 and32 nodes per bank cell.
The original failed qualification and result remain intact. This numerical
amendment changes no position, timing fit, model width, split, or grouping.

After all original runs, automatically re-evaluate ONLY timing integrals that
failed the0.01 audit, using64 and128 nodes per bank cell. Apply the same0.01
qualification threshold. Use the64-node score only if that new audit passes.
Preserve original scores/discrepancies and all refined values in a separate
artifact. A summary may restore qualification only if all original optimizer,
gradient, source-slope, and other target checks pass as well. This is numerical
accuracy control, not a model or reference-based selection.
