# Lag-3 proposal feasibility primitive

This directory is an isolated, research-only feasibility test for the bounded
lag-3 proposal described in `../review/AMBIGUITY_ENGINE_FEASIBILITY.md`. It does
not alter the deployment detector, perform full GLRT confirmation, or claim an
ARM result.

The frozen interface is `Lag3Proposal(rate_hz, edge).run(raw, receiver)` in
`lag3_proposal.py`. `raw` is natural-layout CI16 with shape
`[rate_hz*120/1000, 2, 2]`. Each of at most three candidates exposes the window,
native integer epoch, principal lag-3 CFO, proposal score, direct native complex
correlation, normalized phase support, and separate phase/range/support flags.

Build and test:

```bash
.venv/bin/pytest -q reports/2026_09_27_ds5_cached_tracking/lag3_proposal/test_lag3_proposal.py
```

The one frozen cost invocation was:

```bash
.venv/bin/python reports/2026_09_27_ds5_cached_tracking/lag3_proposal/run_cost.py
```

It failed the preregistered 0.080 ms gate at both rates, so the experiment
stopped before detector replay. See `REPORT.md` and `cost_results.json`.
