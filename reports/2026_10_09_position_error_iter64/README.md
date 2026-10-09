# Iteration64: isolated metadata retries, 2/2 complete

The original DS16-020/S14 and DS16-035/S27 failures remain immutable in
iteration51/results. Both were `KeyError('bank')` during output serialization:
corrected historical baseline documents omit diagnostic bank metadata. They are
not numerical convergence failures and neither member is excluded.

The separately frozen retry uses the original case document's bank/TLE snapshot
metadata for serialization. Session/input/analysis digests and reconstructed bank
IDs are asserted equal. Numerical baseline, observations, priors, starts, c locks,
regional budgets, score selection and downstream model remain unchanged. New
results and caches are isolated; no original executed source/result is overwritten.

![Cohort distributions](../2026_10_09_position_error_iter51/comparison.png)

| Member | Retry status | Arm | Previous research km | Retry km | RMS Hz | Final converged |
|---|---|---|---:|---:|---:|---|
| DS16-020 | complete | fitted-c | 0.075822 | 0.075822 | 75.463 | True |
| DS16-020 | complete | zero-c | 0.663907 | 0.663907 | 141.250 | True |
| DS16-035 | complete | fitted-c | 1.879006 | 1.879006 | 62.918 | True |
| DS16-035 | complete | zero-c | 1.884881 | 1.884881 | 63.493 | True |

Iteration51 incorporates only completed protocol-bound retries, retaining the
original attempt, retry status and result source. Its full148 membership and
DS16 original48/added15 and DS18 prior-registry24/unmatched10 subgroup counts
remain unchanged. No prior registry match is not evidence of independent
validation. Subgroup means never substitute for full-dataset results.

This corrects result serialization, not an inference model or numerical prior.
Freeze0d13db115. Production, public contracts, fixtures, QNAP and RF collection
remain unchanged. The below1km goal is active and not achieved.
