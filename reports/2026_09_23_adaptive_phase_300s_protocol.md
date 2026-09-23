# 300-second adaptive phase scatter protocol

Use the complete device-counter interval [0, 300] seconds of
`scan-hop-28d7592ea614f624`. Color by RF channel 1–4, all lower edge. Preserve
actual time gaps and wrapped degrees; never connect or unwrap retunes.

The exact two-source plot reuses the five previously computed, randomly held
paired-frame double differences **before separate source-rate removal**, with
the saved pair weights. These are all channel 4; the current public phase-blind
bindings contain no two-source measurements for channels 1–3. The time shown
for each point is its held-frame mean device-counter time. No new selection,
fit, alignment, or IQ read is used for those five points.

A separately labeled single-source RX1-minus-RX0 plot provides broader channel
coverage. Replay every one of the 258 visits in the sealed metadata binding;
use its highest-quality phase-blind primary pair, regardless of resulting
phase, control ratio, or coherence. Preserve failed estimates. This is a
different observable from two-source cancellation, not an extension of DD to
channels lacking a second source.

For the single-source replay, reuse the corrected 120 ms frozen-timing frontend:
manifest-bound lower pilot edge; the same RX0 fractional source epoch for both
receivers (the previous replay's conditional common timing convention, not
independently calibrated receiver timing); consistent carrier
coordinate; random whole-frame split with the previous seed/salt; separate
within-frame residual CFO estimation on training frames before symbol summation;
train-only receiver-product rate fitting and held center-phase measurement.
Estimate the raw receiver offset separately in each visit using a 32768-point
FFT of RX1 times conjugate RX0 on the first 2048 samples of each training frame,
Hann tapered and pooled incoherently. Each RX is demeaned per training window.
The peak and a three-bin log-parabolic interpolation provide the coarse offset.
The RX1 acquired carrier is RX0's acquired carrier plus that offset, as in the
previous shared-source gauge. Record its peak-to-median power; do not select or
discard plots by that diagnostic. This extends the prior offset input to visits
without a historical raw-offset audit; it is not a claim that their carrier
aliases are independently validated.

All displayed phases are conditional on source/timing/carrier bindings.
Single-source points may include receiver drift and changing source identity.
Neither plot is a calibrated geometric trajectory or proof of phase continuity
across retunes. Use existing IQ only, with a ten-minute process timeout and
progress every 25 visits. Freeze code and metadata before this replay.
