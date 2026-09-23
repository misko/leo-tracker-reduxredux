# Frozen Astropy TEME-to-ITRS Doppler oracle protocol

Status: frozen before numerical execution on 2026-09-23. This is a bounded
frame and velocity audit. It is not a location fit, physical truth, or evidence
for a positioning-error threshold.

## Frozen inputs and support

- Use exactly the first six TRAIN session IDs in the frozen long-inventory
  manifest, in their published order. Do not read VAL or TEST sessions.
- Use every fixed Sacramento baseline track identity recorded by the sealed
  six-scan synthetic-control materialization receipt. Require one identity for
  every eligible cache-receipt track with at least 3 s support. Bind that
  receipt, its upstream blind baseline, the manifest, every cache receipt and
  state-cache file, and every causal TLE snapshot.
- Read track IDs, timestamps, and support digests from the cache receipts.
  Do not use measured frequencies, training masks, the receiver reference, or
  any position outcome. Use the arbitrary audit receiver at geodetic latitude
  38.0 degrees, longitude -122.0 degrees, ellipsoidal altitude 0 m.
- Resolve each receipt's exact `(snapshot_digest,
  snapshot_collected_utc_ns)` archive instance. Parse its exact TLE payload and
  require every fixed identity to be present.

## State and frame comparison

- For every observation, form the same rounded UTC epoch used by the repository:
  `start_utc_ns + round(times_s * 1e9)`. Propagate the selected TLE directly
  with SGP4 to a TEME position and velocity at that epoch. Do not use cached or
  interpolated ECEF states.
- Transform the same TEME state two ways:
  1. the repository `greenwich_mean_sidereal_time_rad` plus `teme_to_ecef`,
     which approximates UT1 by UTC and neglects polar motion; and
  2. Astropy `TEME(..., obstime=UTC).transform_to(ITRS(obstime=UTC))`.
- Configure Astropy IERS with network auto-download disabled. Record the
  Astropy, ERFA, SGP4, NumPy, and Python versions; the local Earth-orientation
  table class/source where available; every warning; the queried UT1-UTC range;
  and the queried polar-motion ranges. A stale or extrapolated local IERS table
  is a disclosed limitation, not silently refreshed data.
- Compare repository-minus-Astropy position-vector norm in metres and
  velocity-vector norm in millimetres per second. Compute the receiver line-of-
  sight range rate and `-11.2e9 / 299792.458 * range_rate` Doppler for both
  transforms. Remove each track's own mean Doppler before comparing shape, to
  match the downstream per-track CFO nuisance. Report aggregate, per-session,
  and worst-track RMS/max differences; retain per-track metrics for audit.

## Independent velocity check

- At each observation, propagate the same TLE at rounded epochs 0.1 s before
  and after the nominal epoch. Transform positions by each respective frame
  path and estimate range rate from the centered finite difference of receiver
  range. Compare this position-only derivative with that path's velocity-based
  line-of-sight range rate. Report RMS and maximum absolute discrepancies.

## Interpretation and outputs

- This audit has no tuned acceptance threshold and makes no location estimate.
  It tests frame rotation, velocity sign, and Doppler-shape consistency against
  an independent library under the stated local-IERS assumptions. Shared SGP4
  propagation and TLE uncertainty remain common-mode, while Astropy's local
  Earth-orientation data may be stale or extrapolated.
- Write an executable `audit.py`, sealed `results.json`, `results.sha256`, a
  reproducible plot, exact source hashes, and a concise README. Do not modify
  production code, caches, source reports, or archive contents.
