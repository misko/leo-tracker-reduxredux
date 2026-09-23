# Known-solution nesting completion for shared CFO development fits

Freeze before replay. Preserve v1 and v2 unchanged. Reuse all six opportunities,
four feasible snippets, original nominees, random physical masks, and raw hashes.
This is development on previously inspected data, not fresh validation.

Every shared fit is also a feasible independent fit. For each feasible snippet,
run the frozen v2 optimizer in independent mode initialized at the frozen v2
shared frequencies. Require that its initial training SSE reproduces the saved
shared SSE within 1e-9. Include three known feasible independent candidates:
the old independent fit, the embedded shared fit, and its independent refinement.
Choose minimum training SSE with stable ties in that order. Held errors cannot
choose the candidate. Require selected training SSE no worse than shared SSE.

Do not refit the shared arm, modify bounds/aliases/masks, discard any outcome,
or choose new probes. Record every candidate, selected name, closure, training
and held SSE, and optimizer diagnostics. The inclusion check establishes an
ordering among known solutions; it does not prove global optimality or validate
an electrical or geometric model. Bound saved-IQ replay to five minutes and
four 20 ms snippets with no new RF collection.

This completes a necessary numerical check before interpreting the model
comparison. Any phase-geometric claim still needs independent common-state,
frequency-response, timing, and baseline authority. No significance threshold
will be inferred from these reused held responses.
