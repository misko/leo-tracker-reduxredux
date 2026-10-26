# Existing-export proximity inventory

Before computing counts, define this as a descriptive inventory of all original
DS24-0011 winners, with no IQ read, new detector invocation, source reassignment,
satellite search, position fit or geographic evaluation. This is an exposed
development scan and the selected T006 is retained regardless of its counts.

Reproduce the original maximum-margin gate-passing fractional candidate, with
rank tie-breaking. Match every winning observation by receiver/channel/device
counter-derived midpoint and require exact CFO/margin parity. Deduplicate
alternative candidates with the existing `ds23_frame_registration.unique_peaks`
rule: 120 ns circular frame proximity and 250 Hz circular CFO proximity.

A proximity flag requires an additional gate-passing deduplicated candidate
within three circular frame samples and circular CFO distance greater than
250 Hz and at most 5,000 Hz from the actual winner. At 10 MS/s three samples
are 300 ns. Retain both raw and circular distances, margin ratios, every
flagged alternative, all winner/owner denominators, and all 117 original owners.
Do not set a new margin-ratio gate or tune these thresholds after counts.

Two proposals can be aliases, sidelobes or alternative estimates of one signal.
The flag is therefore a reproducible inspection proposal, not proof of a second
source, contamination or an incorrect satellite association. Absence of a
second exported peak does not exclude unresolved interference.
