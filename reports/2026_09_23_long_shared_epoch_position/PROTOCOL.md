# Conditional fixed-identity shared epoch position fit

Use only frozen long-cohort TRAIN[:6] and TRAIN[:16] caches. For each view and
each Sacramento/Reno baseline arm, freeze every track's candidate identity to
the identity selected in the sealed blind tau-zero baseline. This is conditional
fixed-identity inference, not full blind reassociation.

Jointly fit one altitude-zero geographic position and one epoch correction per
scan. Each track retains a free constant CFO profiled on its fixed training
rows. Interpolate the selected candidate's cached state at observation time plus
the scan correction. Hard-bound every correction to `[-5,+5]` seconds and every
position trial to its original Sacramento 250 km or Reno 500 km prior disk.

Run all Gaussian-shaped regularization scales 0.2, 1.0, and 5.0 seconds from the corresponding
sealed baseline position with every tau initialized to zero. Optimize the same
duration-weighted capped-800-Hz track loss plus one prior term per scan:
`800^2 * (tau / scale)^2`, divided by total duration weight before taking the
square root. This scaling makes one scale excursion equal to one one-second
unmatched-track penalty; it is not a calibrated likelihood or prior uncertainty.
Report both penalized objective and
unpenalized train RMS. Do not select a scale or prior by geographic outcome.

Use bounded Powell optimization with at most 300 objective evaluations per arm,
then polish every arm with bounded L-BFGS-B from its better Powell/start point,
`eps=1e-3`, `maxiter=100`, and `maxfun=2500`. Retain the best training objective.
Save all 12 arms
(2 views × 2 priors × 3 scales), fitted taus, boundary flags, termination state,
and fixed identities. Seal inference before evaluating complementary rows or the
reference coordinate. After sealing, report capped/uncapped reserved RMS and
reference error for every arm, plus exact tau-zero baseline parity.

The result is conditional on baseline identities, regional candidate filtering,
one-second state interpolation, altitude zero, capped-loss/prior scaling, and a
local bounded optimizer. No long validation/test or prospective evidence,
deployment, or RF collection is included.
