# Longer sequence support against a strong pilot baseline

Frozen before execution. Reuse the earlier S02/DS7, S13/DS8 and DS9-middle
excerpts, and add S31/S32 (DS7), S28/S29 (DS8), and DS9-first. Both RXs,
first twelve complete frames each: 192 receiver-frames from eight visits.
DS9-first remains included despite its previously poor demodulation. All data
have prior exploratory exposure; additional recordings are new to this estimator,
not prospectively blind recordings. No new RF or geographic fitting.

Re-demodulate digest-verified raw IQ with cached acquisition epoch/CFO. Pilot
initialization is symbols 22–121; the strong frequency-only pilot baseline fits
symbols 22–221. Evaluation is always 222–301.

For each candidate suffix starting at symbol 42, 82, 122 or 162 and ending at
221, use even-numbered symbols to select the 60-state sequence by profiled
complex correlation. Remove the baseline frequency first. Choose the earliest
suffix with coherence >0.5, or the highest-coherence suffix if none qualifies.
Odd symbols in the selected suffix independently verify coherence and fit data
carrier gains. Qualification requires initial pilot, selection and verification
coherence each >0.5. No evaluation samples enter selection or qualification.

Compare strong pilot-only versus a hybrid using the same pilots plus verified
odd sequence symbols. Profile a constant complex gain per carrier, weighted by
sample count, with drift fixed at zero. Also run a k+1 control. Report candidate
arms on all inputs, and a gated hybrid which falls back to pilot-only if
qualification fails. Use identical held samples, retain every failure, and
report per visit/RX and dataset. Do not retune thresholds after observing results.

Measure held-pilot and held-sequence normalized complex squared error, paired
changes, baseline-relative frequency shifts, state agreement across RXs, and
coverage. Neither residual prediction nor cross-RX agreement is absolute
Doppler/position truth. Raw timing is not optimized in this assay.
