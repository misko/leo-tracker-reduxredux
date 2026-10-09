# Controlled qualification of the corrected postfit

Iteration95 preserved the successfully polished ordinary prefit, then stopped:
the corrected fixed-position postfit reported SLSQP success but failed the
unchanged0.001 independent stationarity requirement. Its228 evaluations took
0.62s, so increasing the time limit alone would not address this stop.

Reconstruct the identical ordinary observations, causal satellite bank and
priors through frozen95 code. Repeat its score-only prefit selection, receiver
correction, and corrected objective construction. Verify the saved95 postfit
objective within1e-6 before applying the **unchanged frozen96 polish** to that
exact saved vector:10rounds,100evaluations, fixed128ULP initial-score allowance,
existing feasibility/bounds and full0.001 stationarity threshold. No new seed,
region, hyperparameter, timing prior or gate relaxation is introduced.

This is a shared fitted-c calibration diagnostic. No association, c-arm final
fit or position result is produced. A subsequent separately frozen continuation
must test both c arms and preserve the ordinary operational baseline. A successful
qualification would not by itself establish better localization or prove the
same numerical cause as the prefit failure. Preserve95's failed receipt intact.

No reference coordinates enter inference. No new RF, reserve access, deployment
or production checkpoint mutation. Input and source closure is frozen before
execution. The original96 solver and all95 sources remain immutable.
