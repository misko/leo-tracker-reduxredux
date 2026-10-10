# Bounded retained-region execution

The frozen protocol SHA256 is `d7a7bec07697c851933341abdabb15c578984d3ae96b9d22c05fc78f16f667f0`. Parent verified publication to remote main at `d3550773f467a79b77c27e339b03079bf3103e53` before launch. All 1,555 source and 2,613 input hashes matched immediately before execution; both branches retain exactly three regions.

Initial authoritative sessions: native **36114** (PID **1523736**) and zero **70584** (PID **1523759**). No other numerical worker was active before launch. Both use the pinned production interpreter, `PYTHONPATH=src:.`, `PYTHONDONTWRITEBYTECODE=1`, and OPENBLAS/OMP/MKL thread limits of one. The commands are `148/run.py native` and `148/run.py zero` under that environment.

The unchanged continuation policy allows at most six 500-second slices per branch. Only an explicit matching pending receipt permits another slice. Terminal scientific failures, exhausted budgets, foreign receipts or orphan claims are retained without retry. Progress reads stage coverage and qualification only; reference evaluation is held until both branches are terminal. No new cohort or reserve outcomes, RF collection, production changes or Git mutations are part of this run.

Native process started at 2026-10-10 04:20:52 UTC (process-reported timestamp). Both authoritative sessions ended with exit 0 and terminal `complete` receipts in slice 1; no continuation or retry ran. Known slice runtime was 44.980728 seconds native and 12.585609 seconds zero. All three regions remain visible in each branch; native reached final endpoints, while zero retained three calibration assertion failures and reached no association or final fits. No fallback is imputed.

Postseal report session 9099 ended with exit 0. Fresh native control parity passed for both c arms, including full state and selection metadata. The zero branch has no accuracy evaluation. Frozen sources and numerical receipts remain unchanged; source-only handoff findings are documented separately from those blank failure receipts.
