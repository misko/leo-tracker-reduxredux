# Same-channel cross-dwell CFO prediction feasibility

This audit tests a different idea from the adjacent 10-ms-window tracker:
after a later dwell returns to the same channel and edge, use only causal
standard-GLRT positives from that receiver's earlier same-rate dwell as a
frequency proposal bank. The two-history version deliberately expands every
causal pair; it is an all-positive-bank upper envelope, not a narrow predictor
or proof of persistent emitter identity.

The report also measures a bounded causal drift bank: each unique latest prior
frequency is paired with its nearest older prior frequency before current IQ is
seen; pairs farther than the fixed 20 kHz gate are discarded; one extrapolated
frequency is emitted for each retained latest seed. The fixed gate is a
prototype constraint, not tuned on current-dwell outcomes.

`summary.json` has two deliberately separate inputs. `next_same_channel_smoke`
uses the existing 28-dwell chronological DS7 benchmark, whose 2.5-MS/s first
two visits stay on the same channel. `sparse_history_stress` uses the 704-dwell
stratified ARM cohort; its recurrence gaps are much longer and do **not** test
the next same-channel dwell. Both are labelled **oracle-seeded feasibility**,
because prior positives are supplied by completed standard analysis. Neither
is GLRT recovery or a detector result. A follow-up must run standard GLRT from
the causal proposals against current IQ and score one-to-one individual-hit
recovery, including cold starts and fallback work.

The cohort's same-key recurrence gap is derived from sample counters only
when the sample rate is unchanged. This excludes cross-rate history rather
than inventing a wall-clock conversion. The script contains the metadata
hypothesis `actual_lo_frequency_hz + actual_if_offset_hz`, but standard
acquisition does not consume either field, so the sign and applicability are
unverified. All eligible pairs have zero metadata delta, and the assumption
therefore changes none of the published values.
