# Active continuation: ordinary-start diagnostic and full cohort run

Previous goal turn made progress: froze and launched iteration55, verified first
matched fit receipts, rendered and published its partial report; iteration51
published71/148. Goal remains active and unachieved, no RF/production changes.

Live jobs verified this turn:
- Iteration55 exec3105, Python PID4011107: all192 census endpoints in order,
  both arms.187 feasible=374 fits,5 infeasible=10 explicit skipped receipts.
  Frozen evaluate.py uses no error scoring. Results individually immutable and
  protocol bound; safe resume only after terminal status, skips existing receipts.
- Iteration51 DS16 exec40092 PID4001824.
- Iteration51 DS17 exec53710 PID4001840.
- Iteration51 DS18 exec18770 PID4001893.
  All three remain live. Do not duplicate queued labels or restart on timeout.

Use current processes/receipts as authority. Poll exact handles. Iteration55
reporter uses only completed pairs for provisional score selection, then applies
reference coordinates for evaluation. Initial report only2pairs; no success claim.
Re-run summarize.py in production worker runtime (same environment as evaluator).
Re-run51summarize.py in worktree .venv as receipts arrive and publish updates.

All148 original-policy results are complete and published in iteration45:
DS16 fittedmean5.224km,DS17 .864km,DS18 2.739km. Preserve all original setup
failures and separate retries. The wider-region policy has no changes on first71
completed scans in either arm; DS16-046 rescue is later in the ascending queue.

Critical user clarification is in iteration54 README. Known/reference coordinates
and errors are evaluation-only, never per-scan seeds/banks/retention/settings or
winner selection. Common145 remains a consumed single-scan diagnostic. Iteration55
has ordinary regional starts only, but its budget/sigma were developed on consumed
data. Even a successful recovery requires uniform frozen bank/selection policy
across DS16/17/18 and genuinely independent validation before generalization claims.
The global fixed Sacramento250km prior is an explicit regional assumption.

No recovered-joint seed is used in55. Its frozen model matches52 (common145,
ordinary calibration, relative sigma1/common3,joint100,hard60,local25,20s600).
Five transported endpoints violate residual slope bounds and are never clipped.
Failed stationarity is not accepted merely because solver_success is true.
Report full convergence/failure coverage, score and RMS separately from position.
