# DS21-039 shared receiver residual increments

This fixed-state diagnostic does not establish a reproducible shared transmitter
frequency correction in DS21-039. Most supported channel correlations are small,
one changes sign materially between the two saved solutions, and the edge
channels have inadequate support. These results do not justify adding fitted
transmitter offsets. They also do not rule out beam-specific effects or effects
that this capture's sampling cannot resolve.

The run completed in 28.928 seconds including preparation, using exactly two
native predictions and zero optimizer, objective or gradient calls.
It evaluated the original all-channel and seven-call-refined all-channel states,
both with fitted c. Each state retains 2,798 original training windows and 3,714
native frequency hypotheses. Likelihood and complete objective replay differences
are exactly zero. No reference or held observations were used.

Residual increments use consecutive windows within original training blocks,
receiver, channel and exact RF. Receiver intervals are paired by positive time
overlap and nearest midpoint, with deterministic original-ID ties. Their weights
are the minimum signal probability of the four endpoints. All native and
satellite alternatives are marginalized; assignments are not emitter identities.

| Channel | Original pairs | Refined pairs | Original correlation | Refined correlation | Original / refined weight sum |
| --- | ---: | ---: | ---: | ---: | ---: |
| CH1 | 23 | 25 | 0.224 | −1.000 | 1.166 / 4.54e-8 |
| CH2 | 170 | 146 | 0.056 | 0.050 | 139.735 / 131.437 |
| CH3 | 115 | 108 | 0.052 | −0.285 | 84.407 / 93.625 |
| CH4 | 51 | 61 | 0.033 | 0.008 | 45.762 / 46.884 |
| CH5 | 64 | 63 | 0.170 | 0.107 | 34.313 / 34.528 |
| CH6 | 47 | 71 | −0.221 | −0.133 | 34.876 / 66.217 |
| CH7 | 49 | 42 | −0.034 | −0.004 | 28.056 / 29.894 |
| CH8 | 0 | 1 | Undefined | Undefined | 0 / 0.275 |

Weight sums are support diagnostics, not independent sample counts. Pair counts
can change between endpoints because the posterior signal mass changes. Exactly
zero-mass endpoints remain in the interval inventory and cannot be bridged over.

CH1's refined correlation of −1 is not useful physical evidence: its total
weight is only 4.54e-8, and one pair carries effectively all normalized weight.
Even the original CH1 state gives one pair 84.6% of the total weight. CH8 has no
original matched pair and only one refined pair, so neither correlation exists.
CH3 moves from weak positive to moderately negative correlation; this does not
satisfy the requirement for a shared positive effect reproducible at both states.

Each channel also has 100 prespecified whole-training-block RX1 permutation
controls, seed 20261012, preserving within-block order, intervals and gaps.
Every finite observed correlation lies within its corresponding control range.
These are descriptive controls, not calibrated p-values: support, mixture
composition and block exchangeability are not guaranteed. Broad edge-channel
control ranges and unchanged mappings must not be interpreted as independent
replication. Shared acquisition behavior, retuning or detector ambiguity could
also produce correlation without a transmitter correction.

Independent receipt checks confirm the aggregate 13-file seal and both endpoint
seals. Original held blocks 2, 6 and 12 are excluded, and no observation-center
block differs from its authoritative counter block. CH8's 100 control draws
contain only six distinct block mappings, including 19 unchanged draws; they
cannot repair the missing observed support. The compact
[independent audit](SHARED_RECEIVER_INCREMENT_AUDIT.json) retains all channel
support and control summaries.

Implementation `734c51589` adds an array-only analysis helper and bounded runner;
28 owned tests and Ruff passed. The frozen source closure contains 337 files.
The original source inputs, saved states and numerical cores are unchanged.
The source-only rationale and prespecified procedure are in the
[transmitter dynamics audit](TRANSMITTER_DYNAMICS_AUDIT.md). This is a frequency
residual diagnostic, not a new position estimate or accuracy improvement.
