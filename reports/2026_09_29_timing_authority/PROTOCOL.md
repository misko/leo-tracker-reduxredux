# Independent capture-time authority audit

Metadata only, frozen before execution. Inspect all 72 target recordings in the
nine eight-scan donor-residual plan through AdaptiveHopIqStore(read_only=True).
Bind each manifest digest to its observation export and original plan. Export
the persisted timing authority and terminal counters, without reading IQ.

Independently recompute the three realtime-minus-monotonic offsets, their spread,
first-sample earliest/latest/midpoint and qualification. Compare the observation
export's start against that midpoint. Compare each inherited fitted recording
tau with the relative first-sample host bracket, reporting outside distance.
This comparison is diagnostic: fitted tau may absorb orbit/association/location
error and is not automatically physical clock offset. A host bracket is not an
absolute UTC accuracy bound without clock discipline evidence.

Report all datasets/panels, missing timing, brackets, offset spreads, sampling
rates, counter-duration consistency and software provenance. Do not infer a
sample-clock rate calibration from terminal receipt latency. No fitted timing
prior, RF, host clock changes, collection or geographic refit. One read-only
process with 120-second cap and metadata output only.
