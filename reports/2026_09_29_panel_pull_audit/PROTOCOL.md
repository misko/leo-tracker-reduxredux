# Training-only decomposition of consecutive-panel disagreement

Audit all nine eight-scan panels at their frozen selected positions/timings
under both zero-decay and 10-second likelihoods: 18 diagnostic units. Verify
prior evidence inventories before running. No optimization, geographic scoring,
reference-coordinate use, held-based selection, masking or track removal.

For every eligible track, evaluate the unchanged CovariancePosition training
objective on a one-track document at its panel's fitted E/N and recording
timing. Sum scores/gradients by recording and verify they reconstruct the
complete frozen fit and its held-audit training gradient. Independently check
each recording's E/N gradient by centered 1 m differences (tolerance 0.002).
Keep offset stationarity, complete identities and training counts explicit.

Report first-four and last-four position-gradient vectors (nats/km), their
opposition, per-record vectors, and concentration of track gradient norms:
largest-track share, largest ten-track share, and effective track count
(sum norm)^2/sum(norm^2). Training candidate weights from the frozen result
provide maximum weight and entropy diagnostics; these are candidate-bank
responsibilities, not verified satellite identity probabilities.

At an interior joint optimum, cancelling group gradients are expected and
are not alone proof of model error. Gradient magnitudes are conditional on
fitted timings and offsets, not calibrated location uncertainty. Concentration
uses unsigned norms and cannot establish the effect of deleting/refitting a
track. Different likelihoods rescale gradients, so raw norm changes cannot
be interpreted as accuracy gains. Do not promote a data filter from this audit.

One scientific worker, BLAS1/nice19, 4 GiB address-space limit, 180 s per unit,
and >=5 GiB available memory before launch. Prior eight-scan runs used less
than 0.7 GiB RSS. No overlap with another scientific worker, automatic retry,
new RF, waveform read, provider fetch, propagation, component or fixture change.
Retain failures. This is a bounded diagnostic of existing sealed fits.
