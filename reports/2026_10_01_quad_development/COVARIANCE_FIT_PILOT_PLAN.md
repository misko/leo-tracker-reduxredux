# Fixed sixteen-point covariance refit pilot

The 10-second model beats the trace-matched independent-noise control on conditional added-point prediction in all three fixed pilots. Test geography separately on DS9-B01-S1, DS10-B01-S1 and DS11-B01-S1.

Use sixteen nested points in both arms. First fit `tau10`: retain white/correlated amplitudes and change only correlation time to 10 seconds. Then fit `matched_white`: zero the correlated component and set each track's white variance to match the tau10 model's total dense contrast scale, determined only from observation times and covariance. This control still uses one multivariate Student-t4 per track, so it shares a latent scale and is not a product of independent scalar Student densities.

Both arms initialize from the same original eight-point three-start winner, never from each other or the earlier sixteen-point fit. Retain all physical inputs, sixteen-point IDs, hard association policy, fixed height, Sacramento support, nuisance priors, optimizer and 64-iteration limit. Charge the original cold work to each arm within 90 seconds, leaving five seconds internally and requiring at least ten seconds remaining at admission. Separate fresh-process numerical audits are capped at 90 seconds. Preserve failures without retries.

Require the sealed covariance-port prerequisite before fitting. Reconstruct per-track covariance parameters and selection in the audit, bind initial state/parent, and retain the original objective, assignment, gradient and stationarity checks before geographic scoring. Compare with the preceding sixteen-point default-covariance pilot, which has identical starting state and evidence but historical timing. Do not claim a cold-runtime comparison or independent accuracy validation.

Inspect all six new outcomes before any pair/quad or full-panel expansion. A predictive gain does not authorize promotion, and geographic scores must not select covariance separately for each dataset. The selected tau10 value and matched control remain fixed throughout the pilot.
