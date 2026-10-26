`panel.json` uses the R01 slots/cells schema. `r01_predictions.json` preserves
the exact original forecast object. `r01_prediction_packets.json` uses
`sparse-native-prediction-packets/v1`, with source hashes, target support and
native donor authority from the original public metadata helpers. Use the
unchanged R01 timing adapter, including its legacy midpoint advance.

`r02_predictions.json` contains exact outputs of the sealed R02 predictor on
those packets. Its methods are `linear`, `quadratic_or_fallback` and
`legacy_adapter_linear`. Epochs are already expressed relative to target
window origin for the nominal effective midpoint; do not add another rate
advance. Each method retains its midpoint CFO reference/rate and original
primary donor IDs. Refer to the original R02 interface and source convention
for the constant-epoch approximation.

`protocol.json`, `handoff_protocol.json`, `r01_forecast_seal.json` and
`r02_forecast_seal.json` bind inputs and exact source imports. `verification.json`
and `artifact_seal.json` bind the completed audit. `STATUS.md` reports readiness.
Missing slots/cells are retained. No execution receipt is issued here: root
must bind a separate scoring decision before IQ. No target outcome archive or
position input is produced.
