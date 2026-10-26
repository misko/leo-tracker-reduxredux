# Coherent expansion metadata and exact R01 forecasts

Apply ../../COHERENT_EXPANSION_PLAN.md as the authoritative approved scope.
Use fixed cases DS24-0011 and DS24-0097. Within CH5–8 channel/RX lanes with
new curved native owners, rank by descending new-curved-owner count, then
descending new-native-owner count, channel and native RX. Select at most two
lanes/case. Choose earliest new curved native midpoint, ties stable observation
ID. Do not use confirmation magnitude, CFO, satellite identity, position or GPS
for ranking. Ledger staged additions and graph curved-owner IDs are explicit
RF-selection exposure, not a blind validation sample.

For each selected seed enumerate all same-channel/edge processed20ms source
visits with midpoint in the CLOSED24second interval centered on the seed,
clipped to the processed recording's native extent. Retain both receivers.
If needed take earliest80visits per block before deduplication. At most four
blocks/320paired windows. Missing metadata remains explicit; no replacement.
This approved rule supersedes the older validator proposal's distinct-channel,
half-open interval and70window cap. Fixed-case choice is not recomputed from
later geography or outcomes.

Reuse exact hashed R01 predictor.py, study.request helper, handoff.enrich/native
support helper and validator native observation-ID mapper. Use the original
tracking export only: at most12strictly earlier same-channel/RX/edge visits
within4.5s, unchanged ranks, gates, association, beam, model and uncertainty.
Newly recovered ledger values never become donors. No R02 quadratic or new
timing convention is used. The R01 timing adapter/scorer remains unchanged,
including its legacy midpoint advance and search/frame-partition policy.

Freeze selector/source/tests, RF selection inputs, source tracking/inventory
hashes, selected native panel before prediction. Then freeze original forecasts,
selected donor native index mapping, enriched prediction_packets and input
hashes before IQ. Output the same R01 enriched schema, plus stable native owner
IDs and block membership. Exact target source inventory/manifest/index/IQ digest
and earlier donor native generation are resolved without raw payload reads.

No scoring, raw IQ, validation target outcomes, new RF, QNAP mutation, altered
R01/R02 source or position/GPS input. Metadata authority is not a fresh IQ check
or fresh per-window paired candidate parity. The timing worker must exhaust
each public reader and verify IQ identity. Reused runtime/prior paired-detector
parity evidence must be labeled reuse, not new per-window detector parity.
BLAS1 and580second bounds apply to each stage. Preserve all failures/caps.
