# Matched noncoherent multi-frame support ablation

Freeze before execution. Reuse the same eight visits and two receivers. Partition
evaluation frames 30–79 into five fixed blocks of ten per RX: 80 blocks,
800 scored receiver-frames. Keep every frame. Reuse the already frozen support
decisions from the control-envelope report; verify hashes and decision joins.

Fit one frequency per block, profiling independent static complex gains per
frame/carrier. Use only symbols 22–221 and sum squared correlation magnitudes
across frames (no assumed inter-frame carrier phase continuity). Initialize with
an 8192-point FFT of the full fitting interval and refine within one grid bin.
Evaluate symbols 222–301 using gains fitted on the same frame's training symbols.

Arms: all-frame fit; support-only fit but predict all frames (isolates frequency
weighting); support-only fit plus zero-mean prediction on abstained frames
(adds abstention). If a block has no supported frames, support arms return no
frequency and zero-mean predictions, scoring NMSE one for every frame.
Compare same-support blocks exactly; record all frequency shifts and errors.

This is a matched research noncoherent architecture, not an exact replay of the
production GLRT-64, which uses different symbols and per-symbol correlations.
No production changes, new RF or geography fit. Promote only a meaningful held
benefit over the all-frame baseline; retain the distinction between refusing a
frequency and improving one.
