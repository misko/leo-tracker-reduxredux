# Continuation after iteration53

User clarification audited in ../2026_10_09_position_error_iter54/README.md.
Iteration54 is now the bank/leakage audit, not the proposed refit. Use a new
iteration number for refits. Reference coordinates/errors are evaluation-only;
no per-scan tuning or reference-guided seed/retention/bank/winner selection.
Any common-bank cohort policy must be frozen uniformly for DS16/17/18; common145
is currently a single consumed-scan diagnostic, distinct from live iteration51.
Ordinary-start recovery alone is insufficient for a generalization claim:
new independent validation under the frozen rule is still required.

Goal remains active and unachieved. No production or RF changes.

Original iteration45 lanes have exited; regenerate and publish full148 coverage.
Uniform iteration51 lanes remain live: exec40092 PID4001824 DS16;
exec53710 PID4001840 DS17; exec18770 PID4001893 DS18. Poll rather than duplicate.
They process ascending inventory labels with existing smoke cases excluded.
Each result is immutable; pending prerequisites can resume separately.

Iteration53 completed a census, not fitting: all192 ordinary saved regional
endpoints pass prediction and visibility transport audits;187 are feasible in
the common ordinary calibration frame,5 exceed residual slope60. Original
census.py failed before evaluation due to using calibration-bank indices;
separately frozen census_retry.py fixes final-fit bank binding. Preserve both.
Source hashes verified, all192 original objectives reproduced within1e-6.

Next freeze an iteration54 with matched c0/fitted refits of each feasible census
endpoint on common145, ordinary calibration, sigma1, joint100. Same20s600 budget
per fit; every successful region, both source arms, all3 starting strategies.
Set initial_clock from each saved census clock before each fit. Use saved seed
and common model rebuilt exactly as census_retry.py; no diagnostic recovered
joint starts. Keep infeasible rows, failures and score-selected per-arm winner.
Position reference only after fitting. Expected374 fits; a resumable per-start
receipt is preferable. No exact duplicate removal has been applied yet.
The region inventory budget was chosen on consumed DS18 diagnostics, not fresh
validation. Do not replace cohort results with this experiment.

Previous iteration52 recovered-seed diagnostic got score-selected1.151km fitted,
1.931kmzero under sigma1, but does not show ordinary initialization can reach it.
Iteration49 horizon discontinuities explain many nonstationary stops; do not
accept failed fits merely because the optimizer reports success.

Continue publishing Markdown and plots to remote main after each iteration;
full DS16/17/18 means, matched c arms, exposure labels, membership/failures remain
mandatory. Production hard60 bounded recovery and longest16 trackPNGs preserved.
