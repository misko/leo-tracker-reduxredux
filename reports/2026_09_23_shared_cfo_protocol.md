# Shared receiver CFO: development profile protocol

Freeze before replay. This comparison uses all six existing opportunities and
their already inspected seeded random sample groups; it is **not fresh held
validation**. Do not select a favorable phase or change a nominated carrier alias.

Compare continuous source-specific CFO fits with a common RX1-minus-RX0 CFO
constraint. Both use the frozen sixteen-tone design and per-tone coefficients
constant over 20 ms, fit only on the original training masks. Independent
parameters are four residual CFOs. Shared parameters are the two RX0 source
residuals and one receiver offset relative to the mean nominal receiver offset.
All four effective CFO residuals remain within ±2500 Hz of their original
nominees. A nominal offset closure exceeding 10 kHz cannot satisfy those
bounds; record an abstention rather than changing aliases.

Use deterministic Powell minimization, at most 1200 evaluations/eight iterations,
xtol 0.1 Hz and ftol 1e-8, initialized from the saved training-only grid fits.
Keep that initializer if the optimizer worsens training SSE. Report convergence,
boundary hits, training and held errors per receiver, and coefficients. No held
values choose an optimizer result. The independent arm also gets continuous
refinement so the comparison does not confound the old 50 Hz grid with the
new constraint. Do not interpret nominal optimizer precision as physical accuracy.

Read only the six bound 20 ms saved snippets, verify their original raw hashes,
retain the same random groups and guarded physical sample mask. Bound the
entire run to five minutes. A failure ends the attempt without tuning on held
responses. A common-offset waveform fit is a necessary diagnostic for a shared
receiver model, not proof of zero geometric differential rate or an oscillator
calibration. No orbit or position claim follows directly.
