# Fixed chronological-block deletion audit

For each of DS7/DS8/DS9, take the complete chronologically sorted 30-record
combined panel. Split into five consecutive blocks of six records by index,
not equal elapsed duration. Omit each block in turn, fitting the remaining24.
All15 dataset/block units are required; no outcome-driven deletion selection.
The complete30 result is a comparison, never an initialization or fallback.

Use the unchanged shared track scale likelihood (decay0). Every unit has
three starts E/N(0,0), (3,-3), (-3,3)km with all timings zero. L-BFGS-B settings
maxiter140/maxfun200, ftol1e-14, gtol1e-8, maxls30; bounds +/-12km and +/-5s.
Qualify optimizer success, interior parameters and gradient infinity norm
<=0.01. Select highest training score among qualified starts. No retries,
relaxed gates or baseline fallback. Keep every failure and alternative.

Seal fits before evaluating selected points. Replay training scores within1e-7,
check E/N full-objective gradients at1m/0.5m (tolerance0.002), reconcile tracks,
record IDs and counts. Geographic scoring uses the same exposed unsurveyed
reference only after execution. Report all15 errors and worst cases per dataset,
plus errors for all45 starts. A failure to qualify is not a sub-km success.

Compare held predictions on the retained24 records against the corresponding
rows of the full30 fit, separately by original union/outside panel. These are
matched retained-data comparisons, not prediction of the omitted records.
No omitted-record data may enter the refits. No fresh/blind validation claim.

45 fit processes plus up to15 selected-point audits, each capped180s/4GiB,
at most two workers, BLAS1/nice19. Existing cached inputs only. No exports,
waveform reads, propagation, provider fetch, RF collection or component changes.
