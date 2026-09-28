# Grouped partitions and training-only target forecasts

Scope: implement the first two prerequisites for a receiver detection-order experiment. This stage produces partitions and candidate predictions, not reception-model scores or a new localization estimate. Existing roof recordings are research-exposed and receiver coordinates remain reference-conditioned.

## Partition definition

Use recorded opportunity metadata, never candidate scores, CFO values, detection outcomes, prior association ranks, or position errors, to choose temporal roles. Keep both receivers of every paired window together. Merge intersecting time-support windows within a recording, and merge overlapping same-source signal intervals if they connect additional windows. Connected groups are indivisible across all tracks. Intervals are half-open.

For each recording, let start/end be the earliest recorded window start and latest recorded window end. Boundaries are start + 60% and start + 80% of that metadata span. Groups wholly within the first segment are `train`, groups wholly within the next segment are `reception`, and groups wholly within the final segment are `held_frequency`. A group that crosses a boundary is embargoed. Later roles are forecast destinations only; their candidate outcomes must not participate in reconstruction, CFO fitting or candidate selection.

A separate deterministic whole-recording six/four assignment is metadata for later reception-coefficient calibration/evaluation. Keep the single 7.5 MHz recording in calibration. Assign evaluation recordings only at rates with calibration examples: two 10 MHz, one 2.5 MHz and one 5 MHz, ordered within rate by SHA256 of a fixed documented seed plus recording ID. This does not make reused recordings blind. Every recording may use its own initial Doppler-training prefix to condition target identity; that is distinct from fitting shared reception coefficients.

## Candidate construction

Verify the ten derived cache hashes and original input/analysis authority. Filter raw probe records to complete `train` windows **before** public candidate projection, trajectory reconstruction or graph construction. Do not select tracks from a full-record graph, and do not reuse historical top-three satellite IDs. Later-window detection payloads must never enter training construction.

Apply the existing public trajectory requirements (at least six observations spanning at least three seconds). Bound the pilot to at most three qualifying reconstructed tracks per recording: sort by latest training observation time descending, breaking ties by stable track ID, and keep the first three. This cap is fixed before ranking and applies even if a selected track later fails candidate prediction; do not replace it with a more successful track.

Rank the full eligible causal Starlink catalogue for each selected track, at the known diagnostic roof coordinate and tau=0. Training-time visibility qualification from the public predictor is permitted; future-window visibility must not select or rank identities. Use all observations of that training-only track to profile one constant CFO per candidate and compute SSE; fixed sigma=100 Hz determines normalized top-three weights. Historical associations may supply only a snapshot/provenance binding, never identities or residuals. The new training-subset evidence digest must be recorded and is expected to differ from the old full-record digest.

Build the expensive full-catalogue prediction bank once per recording for the selected tracks, or use equivalent deterministic catalogue batching under the same objective. Forecast only the resulting top three satellite candidates into every eligible reception/held window at its declared midpoint, using metadata timestamps and no later candidate outcomes. Export normalized frequency prediction, fitted training CFO, candidate visibility and line-of-sight geometry with explicit units. These are candidate hypotheses; neither an invisible candidate nor a missing detector event is decoded satellite truth. Keep track normalization/alias and receiver provenance available for a later observation-matching stage.

## Verification and resource budget

Before real execution, test grouping transitivity, boundary embargo, receiver pairing, sample-rate coverage, invariance to changed detection outcomes, and training-only filtering/profile behavior. Freeze exact source, runtime, code and argument hashes in separate launch receipts. Independently check that no shared source group crosses temporal roles and that all forecast target windows belong to their declared later partitions.

Run partition generation and candidate-bank construction serially. Each has one bounded invocation: one numerical thread, nice 19, 4 GiB address-space limit, 300-second wall deadline with five-second termination grace. Preserve failures and completed-record progress; no automatic numerical retry, expanded catalogue search or runtime extension. No raw IQ, new RF, QNAP writes, or position fitting.

Completion means reviewed partition and forecast artifacts, with all ten recordings and exclusions accounted for, or an explicit bounded-run blocker. Even successful completion does not evaluate the detection-order hypothesis: a separate, frozen reception-to-frequency comparison remains necessary.
