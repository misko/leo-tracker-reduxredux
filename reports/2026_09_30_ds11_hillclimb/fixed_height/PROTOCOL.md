# Independently fixed antenna height: preparation

Keep the original causal candidate banks, candidate mixtures, observations,
training masks, per-track CFO profile and east/north/timing bounds. Fix antenna
ellipsoidal height externally; do not add a fitted height coordinate or select
height using geographic error. The receiver ECEF position is the original
ellipsoid surface coordinate plus height times its geodetic up vector.

Preparation verifies synthetic nonzero-height gradients and held isolation,
rejects a fourth optimizer parameter, and checks real-data zero-height parity
on original scans0/16. No position fitting follows until an independently
justified antenna altitude and datum are supplied. Ground DEM elevation alone,
the failed free-height fits, and the reference's horizontal coordinates do not
provide that altitude. Any datum conversion and its limitations must be bound
to a fixed evidence artifact before execution. A newly provided height is a
separate station-calibrated comparison, not proof the historical online system
possessed that calibration.

After evidence is supplied, freeze the numerical height and geographic
comparison protocol before any nonzero-height position fit. Use original IID
and center seeds, select by qualified training likelihood, then assess held
prediction and paired horizontal errors. Do not choose altitude among a sweep.
All broader confirmation requirements remain; preparation does not establish
an accuracy improvement. Children remain bounded to90seconds, with no new RF.
