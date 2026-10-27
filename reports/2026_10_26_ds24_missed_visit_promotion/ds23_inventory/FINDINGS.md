# DS23 compatibility audit for the frozen 10 MS/s recovery candidate

The frozen DS23 manifest contains 413 recordings: 207 fast short-window
recordings and 206 adaptive recordings. Metadata inspection of every fast
recording's listed segment manifests finds only 2,500,000 samples/s. Every
available segment manifest hash exactly matches the frozen DS23 authority;
there are no hash mismatches. No IQ payload or geographic errors were opened.

The frozen R01 scorer in
`/srv/bulk/leo/research/ds24-missed-visit-r01/timing/timing_search.py`, line70,
explicitly rejects any sample rate other than10,000,000 samples/s. Thus none of
the207 DS23 fast recordings supports an unchanged run of this candidate.
Passing a2.5 MS/s waveform as10 MS/s, resampling it, altering timing support or
relaxing that guard would change the scientific application and is excluded
from this frozen promotion evaluation. Adaptive recordings are a different
acquisition regime and likewise do not validate the frozen fast candidate.

All original source/tracking/segment paths are present for204 of207 fast
recordings. DS23-0012,DS23-0184,DS23-0286 retain missing original analysis-input
paths; their raw roots themselves exist. Path presence alone does not establish
IQ integrity, runtime parity or geographic performance. No archive relocation
search was needed to establish the rate incompatibility.

Consequently this study cannot claim DS23 accuracy transfer. Leaving the old
pipeline unchanged on unsupported rates is a defensible operational policy,
but identity with that baseline is not positive evidence that recovery works
onDS23. A later rate-generalized implementation needs explicit signal/null,
native-authority and frequency-uncertainty validation before DS23 localization.

Evidence: `original_path_inventory.json`, `sample_rate_inventory.json`, and the
two metadata-only inventory scripts. All413 original members remain accounted
for. This finding does not imply that2.5 MS/s is physically inadequate or that
sample rate explains existing position error; it identifies implementation
scope only.
