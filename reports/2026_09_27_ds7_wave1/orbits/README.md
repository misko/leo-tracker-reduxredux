# DS7 causal orbit inventory

This reference-free inventory binds the 88 capture identities and earliest
start-time brackets from the sealed budgets plan to locally archived orbital
products. It did not read DS7 pose artifacts, the full dataset manifest, or
reference scores.

For each provider and capture, `inventory.json` records the latest whole
snapshot collected strictly before the earliest possible capture start and a
newest-element-per-catalog-object selection over all such snapshots. Ties use
later collection time and then snapshot digest. Collector time establishes byte
causality; future-dated element epochs would remain eligible and are counted for
audit. None occurred in this inventory.

The first eight composite products were frozen beneath the ignored local
`.leo/ds7-wave1/orbit-products` runtime directory. The report contains their
relative paths, content hashes, member-index hashes, object counts, and every
contributing source digest, but no provider orbital bytes. All 88 captures have
coverage metadata.

The archive exposes two public GP/3LE feeds: Space Track GP and a third party
latest-Starlink TLE mirror. It has no SupGP or provider-ephemeris port or
historical bytes, so those products are explicitly unavailable. Current or
retrospective downloads were not substituted. The mirror is not an independent
orbit-product class merely because it has a different provider label.

These products do not define a candidate bank. DS7 orbit comparisons must use
the baseline's frozen identities, observations, nuisance model, and compute
budget. Any inherited tracking candidate product is site-conditioned and must
be labelled as such; this inventory inspected no observer-site values.

`first-session-fixed-roster-audit.json` applies that restriction to the frozen
baseline bank. The original latest-provider policy is an exact zero-change
control. The all-archive Space Track composite changes six of 129 shortlisted
objects, affecting 26 candidate slots across 23 of 56 tracks, and preserves full
roster coverage. The Hugging Face snapshot changes all 128 shortlisted objects
that it covers and lacks catalog 100009; its changed epochs are older or equal,
so it is a stale-feed ablation with reduced availability rather than a fresher
orbit candidate. No fit or reference scoring was run for this audit.

The gated matched preparation then applied the baseline's stricter `start -
505 s` cutoff. No Space Track snapshot lay in the excluded gap. It retained the
full roster, normalization, observations, masks, shortlist identities and
ordering, and replaced 26 orbital-state slots; all unaffected array rows were
checked for exact equality. Two final root-runner executions produced
byte-identical responses, both converged and interior. Relative to the frozen
baseline control, the reference-free position vector moved 0.0142 m and the
training log likelihood changed by +0.02658. This is numerical zero-change at
the first-session smoke scale, not a reference-scored improvement. Full hashes,
the excluded transport attempt, and execution provenance are recorded in
`matched-comparison.json`.
