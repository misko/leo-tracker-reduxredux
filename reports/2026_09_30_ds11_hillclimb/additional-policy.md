# Frozen additional-recording check

Declared before exporting or fitting any of the twelve additional recordings selected in `additional-plan.json`. They are deterministic chronological ranks among the 55 DS11 captures excluded from the original 32, not an independent site or chronological holdout. Their position outcomes have not been inspected in this hill climb.

Freeze the source_receiver_equal model and its physical-identity grouping unchanged. Each new recording first receives the original IID fit from three generic starts; that same-recording fit initializes the challenger alongside the generic starts. The challenger is selected exclusively by qualified training score. If no challenger start qualifies, use the qualified original IID estimate. If the original IID fit fails, preserve that recording as a policy failure. This qualification-only fallback is declared after observing the boundary failure at original index26; it is not a claim that the raw source model qualified on all32.

The policy must lower both the median and P90 reference error on the twelve additional recordings, improve at least six positions, and retain all twelve qualified outputs to count as successful replication. Report all attempted recordings, raw challenger qualification, fallback count, original-matched metrics, and common-IID held diagnostics. Do not choose a different weight or fallback based on these outcomes.

Original-panel policy metrics: 32 outputs, one IID fallback, 21 paired wins; median2300.225m versus2759.383m, P906029.005m versus7708.225m. Remaining24 policy median2579.029m versus2655.353m, P906338.732m versus7961.331m. The raw model's successful-only medians must not replace these full-denominator comparisons.

Use existing on-disk GLRT products and archived causal TLE inputs only. Each export is capped at180seconds and each fit at90seconds; at most three single-thread numerical processes overall. No radio collection or QNAP writes.
