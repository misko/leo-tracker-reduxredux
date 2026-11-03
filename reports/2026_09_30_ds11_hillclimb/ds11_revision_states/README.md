# Older causal orbit states prepared with exact original-bank replay

Both DS11 pilot exports complete successfully, preserving every track,
candidate slot, observation time and timing-grid node. Repropagating the pinned
original elements reproduces saved position and velocity arrays exactly:
maximum discrepancies are0km and0km/s in both scans.

| Scan | Tracks | Candidate-track occasions | Export time s | Original-state replay |
|---|---:|---:|---:|---|
|0|62|760|4.03|Exact|
|16|58|666|4.39|Exact|

The older arrays are saved separately in `00.npz` and `16.npz`; original banks
and archive bytes are unchanged. Metadata binds the full source inventory,
exact archive occurrences and elements, observation/bank digests, runtime
propagator source, physical identities and output bytes. No missing candidate
or propagation failure is hidden by deleting a slot. All older states are finite.

Two component tests pass for candidate ordering, missing slots and duplicates.
Independent verification rehashes all sources and outputs, checks serialized
key/shape/order coverage for all120 tracks, and repropagates the first/last
candidate on the first/last track at boundary observations/timing nodes. Those
older-state spot replays agree exactly. Full original-state replay was performed
by the exporter; independent older-state replay is explicitly a spot check.
Both single-thread processes exit0 under90second caps, without retries.

These arrays enable position- and timing-dependent older-minus-original Doppler
directions. Successful preparation is not evidence of improved orbit truth,
calibrated covariance, authenticated identity or lower geographic error. The
next model must preserve shared source coefficients and candidate uncertainty,
and compare against a zero-revision joint-identity control before attributing
effects to the historically learned uncertainty prior. No reference coordinates,
held residual score, position fit, new IQ or RF collection is used here.
