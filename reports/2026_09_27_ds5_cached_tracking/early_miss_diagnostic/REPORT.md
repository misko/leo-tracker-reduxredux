# Adjacent integer timing explains recoverable margin failures

The two-target diagnostic completed with stable sources and unchanged input
arrays in 0.12 seconds. All eleven cold acquisition proposals per target were
scored at rounded timing and adjacent integers, with acquired and expected
physical frequency unchanged. The original discovery-positive veto was retained.

At 2.5 MS/s visit 1089 RX1, probes 3 and 4 pass at the rounded epoch but overlap.
Probe 8 passes at a different physical-frequency identity. Probe 10 fails margin
at the rounded epoch (0.02091) but passes one sample earlier (0.03407). Combining
probe 3 at center and probe 10 one sample earlier provides a frequency-compatible,
non-overlapping pair. The receipt's `pairs_by_offset` deliberately uses one
common offset; its empty lists do not rule out this mixed-offset pair.

At 5 MS/s visit 1104 RX0, probes 0, 3 and 7 are just below the unchanged 0.025
gate at center (0.02431, 0.02408, 0.02458). One sample earlier enables several
non-overlapping pairs, including probes 1/3. Some adjacent points have frequency
status failures and must not be accepted merely for a high score.

The separate `early_local_tracking` candidate chooses among three eligible
integer points per proposal, and its causal development replay subsequently
recovers both identities. This diagnostic alone would not establish causal
recovery, reference association, or safe behavior on negatives. One diagnostic
helper test passes. No held-out IQ or frozen detector was changed.
