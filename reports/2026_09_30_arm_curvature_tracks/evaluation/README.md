# Curvature track membership evaluation

The primary comparison uses only exact lane, canonical recording source
identity, and same-source measured CFO modulo the normalized alias spacing. It
does not use candidate IDs, ranks, track IDs, satellite labels, or the TRACK
row's compatibility-only linear summary.

Thresholds were frozen before curvature outputs were inspected. A conservative
complete association requires at least 80% reference-source coverage and 80%
purity among output points centered inside the reference interval, with each
shared point pair agreeing within the deployed 2500 Hz residual gate modulo
alias. Maximum-cardinality one-to-one assignment prevents counts from being
inflated. Split and merge edges, union source coverage, time coverage, and
overall output purity remain visible separately. A long nonlinear arc may
legitimately cover several server linear segments; merge evidence is therefore
a segmentation difference, not an error or a physical-identity result.

Time evidence has two names with distinct meanings. Support-interval occupancy
is the union of the short detector integration intervals divided by the full
reference duration; it is expected to be small for sparse 20 ms evidence and is
not continuity. Source-center span is the distance between the first and last
consistent source centers divided by the reference duration. Neither is a
primary eligibility gate.

The maintained server result is only a comparison proxy. There is no
independent satellite identity ground truth in this evaluation. The old linear
curve association is retained as an explicitly secondary diagnostic because a
curved track can fail it despite recovering the same measured observations.

For each reference segment the report also computes an input-evidence ceiling:
the fraction of reference sources for which *any* candidate in the evaluated
input has the same canonical source and agrees within the 2500 Hz modulo-alias
gate. A segment below 80% at this stage is data-limited for the primary gate;
it is kept separate from an algorithm miss. Source availability without CFO
agreement is reported alongside the stricter ceiling.

`baseline-server-self.json` exercises the complete 10,066-observation server
branch and recovers all 63 reference segments. `baseline-arm-linear.json`
exercises the complete 9,728-observation ARM branch through the current linear
tracking result: 11 of 63 references are data-limited, so at most 52 can meet
the frozen coverage gate. The current grouping completes 42 primary
associations. Its secondary legacy result is 42 strict and 57 relaxed. These
baseline files validate the evaluator paths; they are not curvature results.
