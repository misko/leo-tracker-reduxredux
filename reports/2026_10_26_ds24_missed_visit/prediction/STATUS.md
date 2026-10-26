Completed development metadata stage. Only prediction/ is edited. No validation
tracking files or raw IQ opened. See FINDINGS.md, summary.json and the separate
posthoc timing_diagnosis.json. Frozen rules were not changed after evaluation.

All 288 paired targets have public metadata; 576 forecasts reproduce and pass
fresh target-response redaction. 453 cells have forecasts versus 188 latest-visit
donors; 123 no-donor cells remain. 165 targets have original gatepasses, 162
also forecasts. Primary compatibility at 500Hz is 10 cells within 2 samples,
143 within 16; any eight modes give 25/147. These are target-chosen archived
compatibility, not signal recovery. Fixed CFO-only-match diagnosis: 144 cells,
signed timing median −5.58 samples, fitted median|error| 5.61 versus carry 29.74.
Per CH/RX/gap/count results retained.

Exact seals: protocol f31f786c6231be33497faf4071c32ffb6d9f6574fabae3cb4fbba262e8fc771d;
predictions 157cc6664b88f8fc1f2b481256b58b5c76598050fb63e7943e920d0dad7d9992;
native packets ae1183913e40a37258c5bdf048459fc4cf3526928b119dfd55119bb3d17aa721.
prediction_packets.json is the timing-worker native-ownership handoff: exact
integer generation is distinct from stream_generation; all 1,395 donor windows
have verified public index metadata. Five tests and the full audit pass.

REPORT.md is the concise report; FINDINGS.md has full detail and five PNG/PDF
figures. Separate posthoc earlier-donor diagnoses support curvature and a
suggestive RF-scaled magnitude, but do not establish physical sign or identity.
ROUND2_PROPOSAL.md contains the conservative independent-quadratic proposal;
it has not been implemented or run. The sealed round1 predictor is unchanged.

Interface: panel.json.slots[*] binds request_id/case/channel/fraction, target
public raw_authority, and cells[*].header/history. Header includes native start,
stop/window length, rate, edge, generation, source_id, RX, actual RF and tracking
source hash. history includes earlier public persisted probes only. Archived
target candidates reside separately in evaluation_targets.json.

predictions.json.rows[*] repeats header and forecast. forecast.modes[*] contains
hypothesis_id, donor observation IDs/ranks/native support, model (CFO/timing fits
at explicit latest-donor reference_counter), full prediction and halves[0/1].
Each prediction has start/stop/reference counters, epoch_samples, CFO_hz,
CFO_rate_hz_per_s, timing_rate_samples_per_s, heuristic sigmas/three-sigma widths.
Timing phase is evaluated at each support START; CFO is evaluated at its
midpoint. The model has separate timing_reference_counter and CFO
reference_counter. Within-support timing drift is an explicit constant-epoch
scorer approximation (<=2 samples over 10ms at the 200samples/s bound).
Use each half's own epoch/CFO/reference; predictor.propagate(model, rate,
start, stop, reference_counter) also supports a per-frame reference. There are
at most eight alternative modes, at most two paths per latest donor, no fresh
independent donor observation, and no implied probability calibration. Missing
visits and one-donor fallback remain explicit. Target outcomes never select modes.

example_packet.json is fabricated and ready for the timing worker. Five owned
tests pass, including missing visits, alternatives/rank caps, causal redaction,
large counters, known nonzero rates, and correct full/half reference conversion.
