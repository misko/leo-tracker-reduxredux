# Original-state nonlinear calibration promotion preparation

Receipt-only iteration149 diagnosis: all three zero discovery states independently
qualify under c=0 but fail fitted-c KKT at 45.732,147.433 and85.081. The first
Newton attempt uses46 evaluations and accepts no round. Its full step improves
objective but worsens KKT; its half step improves both, yet unchanged102 chooses
the lowest-score candidate, rejects its worse KKT and stops. The other two attempts
use91 evaluations and two accepted rounds, reduce KKT to0.788 and1.648, then stop
at the round budget. Reduced Hessians are positive definite, tangent dimension21,
with no active constraints. No change to102 damping or acceptance is proposed.

Apply the same rule to both branches. Bind each ORIGINAL discovery vector,
objective and bank; audit its original arm and fitted-c KKT. If fitted-c fails,
run existing bounded SLSQP from the ORIGINAL state, never a149 promoted state.
Keep position fixed, free c, slope bounds ±60 Hz/s, and an optimizer cap of
5 seconds or 200 iterations.
Independently audit selected objective, feasibility and KKT; reject worse objective
or moved position. If still unqualified, use unchanged102 once, two rounds and
at most100 evaluations. Require independent final0.001 gate before unchanged103
fresh calibration,105 regional continuation and B7.

Original zero-arm audit locks static c; final zero-c also locks downstream RF-time
terms. No region reranking, bank change or relaxed constraint. Original payload
and identity remain unchanged. Clone105 function environment with explicit port,
without mutating loaded globals. Preserve original states, both audits, nonlinear
fit/solver diagnostics, evaluations, elapsed time, polish, failures and promotion.

The5-second cap concerns optimizer evaluation/callback deadlines, not total stage
wall time. Postfit summarization and audits add overhead. Receipt and enclosing
stage elapsed times report actual cost. Nonlinear objective calls have no count
cap. Audit accounting separates two original audits, one nonlinear selected audit
and one final audit; excludes optimizer calls, up to100 polish calls, coarse
repricing, validated postfit and downstream calls.

Exactly three sealed regions,25km radius, six500-second slices per branch,
exclusive claims/no retry, fresh native control, at most two single-thread workers.
No new search or RF. Source/input authority inherits149/148 and adds150 sources
and independent REVIEW.md. Public148 reporting only after both terminal, with
full-state control parity. Consumed mechanism pilot, not independent validation
or an official mean update.

Preparation only. No protocol freeze, model calls or launch. Independent review
checks wrapper, ports, source closure, synthetic failures and original binding.
