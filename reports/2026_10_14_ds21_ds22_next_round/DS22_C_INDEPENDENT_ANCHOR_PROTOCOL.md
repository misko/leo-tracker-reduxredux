# C full-band anchor/profile/release diagnostic

Prespecified cases: DS22-001 and DS22-003. This test asks whether independent
half-band geographic solutions can lead the unchanged full-band C objective
to a better stationary solution. It follows the completed independent001
comparison; independent003 is still being generated. It does not import
reference coordinates, independently selected candidate pools or half-band
calibration parameters into the full-band objective.

For each case, use the sealed original full-C training winner and the sealed
independent lower/upper C training winners. Only the latter two geographic
coordinates become anchors. Keep the original full candidate bank, native
evidence, timing parameterization, calibration model, receiver ambiguity
inventory and priors. Every anchor starts with the same original full winner's
non-geographic parameters and nuisance coefficients.

Ordered anchors: original all, independent low, independent high. At each,
first hold geography fixed and optimize the remaining original parameters;
then release geography in a new25km disk centered on that same anchor.
Each stage has20seconds/600iterations, fitted c only. A nonstationary profile
skips its release. Maximum six calls per case, twelve across the pair. Select
only the lowest stationary released training objective, ties in anchor order;
retain all outcomes and do not automatically replace the original incumbent.
The all-anchor chain is the matched continuation control.

Before any optimizer, qualify the genuine source/input closures, independent
terminal selections, exact model layout and original objective replay. The
existing optimizer initializer reserves a tiny timing-bound margin: if an
original stationary endpoint lies exactly on that boundary, record its exact
initializer transformation. Permit only a timing-only change below1e-8 in
physical-vector coordinates, applied identically to every anchor; reject any
calibration, nuisance, geography or larger timing change. This is an explicit
numerical initialization rule, not a relaxed endpoint acceptance test.

Each case has an internal180second budget, TERM195/KILL200; at most120seconds
are optimizer calls. Use separate immutable namespaces and durable per-stage
launch/termination receipts. No retries. Bind all sources and qualified starts
before fitting, and require both case seals before any new configured-reference
join. Position distances retain the DS22 configured-unconfirmed caveat.
Report training NLL, priors and post-seal distance separately; no conclusion of
better localization from training score alone.

This is a basin-reachability diagnostic with additional independent upstream
computation. It is not an equal-end-to-end-budget channel ablation or a validated
full-dataset algorithm. Existing frozen source files remain unchanged. No
anchor fits have run at this protocol's creation.
