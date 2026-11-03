# Time-aware joint-position evaluation

The common-persistence donor ablation passes the unchanged transfer gate: 28/38
source wins, held score above receiver/elevation and swap/permutation controls.
Freeze its donor-only parameters and tau=7.8984961243 s. Replace independent
conditional RX factors with the tested normalized sequence filter. Use paired
window midpoints for dt; use the original bank LOS at observed point times.
Marginalize held receiver states when computing training sequence likelihood.
All track memberships/times remain conditioned design variables. The same
ownership, matching, satellite factors and CFO profiling remain in force.

Before fitting, verify zero-correlation parity with the previous independent
solver and full-objective derivatives on pilot scans 0 and 16. Fit receiver-only,
signed, swapped and permuted arms on all six compatible original scans and the
one additional recording. Reuse the identical Doppler-only comparator; do not
refit or recalibrate it. Original IID seeds, EN +/-12 km, time +/-5 s, L-BFGS-B
and 90-second child limit, qualification thresholds remain unchanged. Save all
28 fits before geographic scoring. Preserve every failed or timed-out cell.

These seven recordings have now all been inspected under the previous model;
none is a fresh blind holdout for this follow-up. Keep the additional recording
reported separately. A development gate requires all seven primary fits
qualified, >=5/7 wins against joint Doppler, >=10% median reduction, no worse
P90, and no regression on the additional recording. This is not independent
surveyed validation. Full absence/clutter, new orbits and antenna width fitting
remain outside this conditional experiment.
