# Early timing/position interface feedback

Frozen before outcomes, 2026-10-26 21:29 UTC. This branch will read shared
artifacts here; no change to public persisted contracts is proposed.

- Keep all requested cells, with missing/ambiguous/no-donor states. Separate
  original full-window acquisition exposure from search and confirmation scores.
- Give each native target a stable source+RX+counter owner independent of timing
  hypotheses, aliases, frame halves and proposal rank. Include exact raw IQ
  authority/generation, native receiver ID, sample rate, actual RF and edge.
- For each hypothesis retain original donor IDs/ranks/counters, gap/missed-visit
  counts, timing/CFO reference time and rates. Preserve modes; do not use the
  target winner to choose donors. Propagate rates to each half/frame explicitly.
- Freeze one search winner (timing and original mode) before confirmation. Keep
  the selected proposal and every tested search location in an exposure ledger.
  Use disjoint native confirmation support, and no confirmation retuning.
- Output the unchanged later-sample scorer's CFO and gate separately from donor
  carry/prediction. Search and confirmation CFOs share a target owner; they do
  not both enter position fitting. Label the timing/search conditioning. Do not
  supply a donor-conditioned posterior as an independent Doppler likelihood.
- Match complete search exposure in nulls, with at least 32 independent later
  vectors per applicable exposure stratum. Report observed rate plus exact 95%
  upper bound; the practical exploratory threshold here is observed <=5% and
  upper <=10%. Do not promise a global family-wise guarantee from this panel.
- Strong known-truth frequency screen: >=20 independent trials, >=90% within
  500 Hz and no admitted >1 kHz failures. Include Doppler evolution and both
  signs of donor CFO/timing errors. Keep availability and weak controls visible.
- Supply a development candidate manifest distinguishing corrected original
  winners from newly present native targets. A sparse panel is an opportunity
  screen; any coherent follow-up block nomination must be frozen before its raw
  target scoring and cannot choose satellite identity or use position errors.

Suggested research handoff fields: case/request_id, stable target ID, native
support/header, original owner status, donor provenance, all proposal exposure,
search-selected mode/timing and score, sealed-before-confirmation receipt,
confirmation support/CFO/gate, known-control stratum, null policy receipt,
new-versus-correction action, availability/rejection reason. Later position
readiness is a separate manifest after graph/causal-association review.
