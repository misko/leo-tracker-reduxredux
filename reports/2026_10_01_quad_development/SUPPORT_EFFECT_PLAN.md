# Finite-support size-of-effect audit

Use the three first-single baseline states and signal associations, exact retained quality joins, and existing orbit interpolation. No optimization or GPS scoring. Read and snapshot the pinned public geometry source first. The exported factorial moments represent equal-weight symbol-center offsets: m0=1, m1=0, m2=E[dt²]/2, m3=E[dt³]/6. They do not prove the detector's exact frequency-estimator weighting.

Compute the cubic Taylor support correction delta = m2 f''(t) + m3 f'''(t), using symmetric differences with h=0.02 and 0.04 seconds. Reproduce existing point-time Doppler contrasts including fitted receiver drift before comparing. Report support spans, correction magnitude, step-size agreement, contrasted correction whitened by the existing covariance, and changes to residual energy at fixed state. This is a moment approximation, not an exact detector response or rigorous remainder bound.

Only investigate a localization implementation if some track's whitened correction norm exceeds 0.01 (one percent of one aggregate standard-noise unit) and the two step sizes agree within 10% or 1e-6 Hz absolute. Otherwise stop the finite-support localization expansion on these pilots. This size gate is predeclared, not a geographic accuracy gate. It cannot rule out other timing, estimator or RF bias.
