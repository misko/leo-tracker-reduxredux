# Alias-convention audit and corrected cross-visit replay

The localization export uses canonical-RF, dealiased CFO. Previous research
cross-visit fits used raw cached CFO plus actual RF and omitted visit-dependent
alias indices. Correct this implementation mismatch before interpreting them.

For every selected visit, verify
`native_dealiased = measured_hz * actual_rf_hz / 11.2e9` and
`(native_dealiased - cached_cfo) * 4.4e-6` is an integer within1e-8.
Also verify exact track/visit/time/RF and source hashes. The integer here is the
additive correction; the deployed relative_alias_index has the opposite sign.
Check that each lane's RF remains constant. Keep the existing alias assignments;
do not infer new assignments or use held values to change training hypotheses.

Replay both prior two-point and four-point studies with the native dealiased
training frequencies. Reuse their frozen long-pilot residuals and, for four-point
fits, frame-jackknife weights. Evaluate on identical held pilot samples, using
the held dealiased CFO as demodulator reference (equivalent modulo the pilot
symbol frequency period). No new RF, extraction, selection, fit thresholds or
quality filtering. Preserve all failures and short held coverage.

Before correction, reproduce the prior per-frame NMSE at its saved predictions
within1e-10. Corrected fits use the same prior methods/splits. Report all tracks,
alias variation, and means weighting each track equally. Use1e-10 NMSE for
descriptive win/tie/loss counts to suppress floating-point ties. This is a
research-assay correction, not evidence of an operational localization bug.
Numerical cap120seconds, one process/thread. No geographic claim from this replay.
