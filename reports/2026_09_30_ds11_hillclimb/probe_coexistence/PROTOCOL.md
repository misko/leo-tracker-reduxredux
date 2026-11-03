# Bounded common-sample pilot coexistence pilot

Use original scan0 and its frozen training source-group sidecar. Sort shared
probe group IDs lexicographically, select the first two distinct training
candidate IDs within each, and take the first six groups with at least512
common fitting samples and256 common held samples in their first frames.
These eligibility decisions use metadata and known symbol timing only.
Record every considered group and reason. No position or waveform score
selects a group. Freeze candidate epochs, frequencies and source identities.

Use raw5MS/s samples that lie0.8–3.6microseconds inside each candidate's OFDM
symbol. Fit on the intersection of symbols22–221 for both candidates; evaluate
on the intersection of222–301. All arms use exactly the same raw samples.
Fit per-carrier complex gains only, with acquisition frequencies and epochs
fixed: candidateA, candidateB, their sum, A plus an11-symbol-rolled B pilot,
and B plus an11-symbol-rolled A pilot. Report all held NMSEs, ranks and
conditioning. Neither gain fitting nor selection uses held samples. The model
includes only known pilots, not a full unknown-payload or interference model.

Use three fixed positive-control excerpts from the prior scan0 waveform
inventory, ordinals0,55,110, with the same single-candidate pilot model and
its rolled-code control. Do not replace weak or unavailable controls.
Synthetic tests cover one versus two signals, held isolation, and an independent
native-IFFT/CP/resampling check. Real controls assess whether this simplified
waveform convention transfers to the existing corpus.

One metadata-preparation process capped at180seconds, no IQ; then one worker
capped at120seconds, one BLAS thread, nice19. Read six existing visits through
the public read-only store, validate published recording manifest and chunk
digests, and preserve excerpts/results. Record active rows before reads and
retain all failures without retries. No new RF, QNAP mutation, geographic
scoring, satellite identity claim, frequency refinement or position fitting.

Treat joint improvement over both single models and both rolled controls as
conditional evidence for two pilot contributions. It is not a calibrated
likelihood ratio, a false-alarm probability, proof of independent satellites,
or authorization to impose independence/exclusivity in positioning. An absence
of improvement also does not prove exclusivity when this model is inadequate.
