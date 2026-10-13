# DS21-009 three-model initialization: v2 succeeds

The revised A/B/C adapter completed DS21-009 initialization without any position
fits or reference evaluation. Two Model B all-band seeds required independently
verified transfer of their original source coefficients after the strict
projection reported nonconvergence. Their maximum physical correction mismatch
is 7.276e-12 Hz. All required compatibility and feasibility checks passed.

| Model/view | Original strict projection | Verified source transfer | Other initialization |
| --- | ---: | ---: | --- |
| A / low | 6 | 0 | — |
| A / high | 0 | 0 | Six timing-only seeds; unused calibration omitted |
| A / all | 0 | 0 | Six placeholder seeds, fully overwritten by original sequential core |
| B / all | 4 | 2 | Fallbacks are `cold-0` and `cold-1` |
| B / low | 6 | 0 | — |
| B / high | 6 | 0 | — |
| C / all, low, high | — | — | 18 unchanged native seeds; six all-training receiver lifts |

The fallback residual RMS values are 2.062e-13 Hz and 4.988e-13 Hz, respectively.
Both record verified frame, clock basis, coefficient bounds and timing bounds.
Neither is a stationary location fit. No failed solver coefficients are adopted,
and successful strict projections are unchanged. The original v1 failure and
its diagnostic remain intact.

Several transferred clock coefficients are numerically at their ±2,000 Hz
bounds: their saved values are ±1999.9999999999995, only about 4.55e-13 Hz
inside. V2's exact-equality `active_bounds` list is empty, whereas SciPy's
tolerance-based mask flags such coefficients as active. This is a reporting
convention difference, not evidence that saturation disappeared or that the
source coefficients moved into the interior.

Implementation `7d83e159f` and the independent review are documented in the
[v2 protocol](THREE_MODEL_EXPANSION_V2_PROTOCOL.md). The protocol binds 411 source
files; all 410 v1 dependency hashes remain unchanged. The initialization SHA-256 is
`94fe216c7568874fe24c515003d921833dedbfdf00a252d8b8f4bdf0cfda7ece`.
The [independent receipt audit](INITIALIZATION_009_V2_AUDIT.json) records source,
parent, seed-method and original-success comparisons.

This resolves the demonstrated initialization failure. The next step is the
original 12-unit, at-most-54-fit A/B/C comparison, followed by sealing and seven
reference evaluation rows. No accuracy improvement is established by successful
initialization, and the full-DS21 0.5 km target remains unmet.

The first subsequent path, A-0, saved three stationary low/high/final fits and
a complete slice receipt. Its post-run validator then rejected a descriptive
field: the frozen sequential core sets high-stage `training_high_fractions` to
`None`, while the raw fit receipt contains `[0.5, 0.5]`. All other raw high fit
fields match; low and final fit dictionaries match exactly. The command exited
with this validation error after writing the results. Those fits remain intact;
they are not being rerun. A narrowly versioned metadata-validation correction
is required before the overall comparison can be sealed or evaluated.
