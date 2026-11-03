# Tuned-center versus nominal pilot-center normalization

Freeze before execution. Use all 3,983 conditional residual cases in nine target
panels. Read the installed public starlink_edge_rf_center_frequency_hz contract
for nominal pilot-band centers, recording source hash. Join channel from pinned
observation exports and select the nearer lower/upper nominal center, requiring
distance <=1 MHz and an unambiguous nearest center. This is a convention assay,
not an independently measured transmitter frequency.

Existing canonical observation y = raw_CFO * 11.2GHz / tuned_RF. Compare nominal
pilot-center normalization y_new = y * tuned_RF / nominal_pilot_RF, keeping the
predicted canonical Doppler, fitted location/timing, candidate, masks and 100-Hz
model scale fixed. Profile the constant using each arm's own training mean.
Report full and changed-RF cases, factor ppm, training-centered observation
change RMS, maximum centered change, and paired held median-absolute error.
Constant RF offsets are absorbed by each track's existing nuisance constant.

No geographic fit, RF collection, metadata mutation or production edit. No
physical calibration or accuracy improvement follows solely from small residual
changes. Keep all missing/mapping failures explicit rather than guessing a band.
