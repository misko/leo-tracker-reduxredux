# Prefix-track competition and forecast-age diagnostic

Use the original ten-record pilot and four-record DS8 datasets and their exact
bound training-only alias mappings. Preserve all nominees, windows, recording
split labels and empty receiver candidate sets. This is exploratory diagnosis of
previously evaluated data, not a model improvement or new confirmation.

Audit whether distinct mapped prefix tracks in the same exact RF lane contain
distinct candidate observations in the same source windows on the same receiver.
Report shared candidate identities separately. Coincident detector candidates
demonstrate recorded multiplicity, not distinct physical satellites.

At every later window, preserve the frozen satellite forecasts and measure
wrapped nearest-candidate compatibility within the existing 500 and 1,500 Hz
thresholds. Compare (a) original normalized nominee-weighted support, (b) the
maximum over track-conditional weighted supports, and (c) any stored nominee
compatible, including zero-prior alternatives. The latter two are optimistic,
outcome-selected diagnostic ceilings, not valid predictive likelihoods or deployable
models. Empty or invisible observations contribute zero. No gate or prior changes.

Export per-track prefix support counts/start/end and forecast age since the last
prefix support. Require mapped support to precede scored observations. Aggregate
windows within recording/role then weight records equally, with calibration and
evaluation splits kept distinct. Do not claim that changing track competition
fixes forecast aging solely because an optimistic ceiling increases.

Freeze source, tests, protocol and input byte hashes before each real run. Each
run is limited to 120 seconds, one numerical thread and 4 GiB. No RF collection,
IQ detector run, model fit, new orbit propagation or QNAP mutation. Independently
audit overlap and support calculations before reporting conclusions.
