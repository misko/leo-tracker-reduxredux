# Matched continuation of the sealed DS18-022 search experiment

Preparation only: no protocol has been frozen and no recording computation has run.

The primary comparison continues the three sealed fitted-native discovery regions
and, separately, the three fitted-fixed discovery regions from iteration116. Each
branch uses the same existing iteration105 `recovered_region` calibration,
association and bounded regional finals, followed by unchanged B7 joint stages.
Every retained region receives this direct calibration path. Thus native is a
matched research control, not an exact replay of deployed ordinary calibration.
There is no union of discovery policies and no winner selection across them.

Both final c arms share their branch's fitted-led regional winner and stage support,
as B7 requires. The zero-discovery queues remain a separate deferred sensitivity:
their constrained coarse endpoints are not silently treated as fitted-c prefit
solutions. Static c and the final two RF-time terms are locked by existing B7 in
the zero-c final arm. Sigma125Hz, common timing sigma3s and relative timing sigma2s,
hard60 slope bounds, existing
calibration/clock priors and the independent KKT0.001 gate remain unchanged.

Exactly three regions at12.5km separation are retained per branch. No broad coarse
recovery or additional25/50km discovery pass occurs. The published116 continuation
plan's phrase “receiver-clock discovery passes” was incorrect: production B7's
three ordinary passes use regional retention separations12.5/25/50km. This additive
clarification leaves that published hashed artifact unchanged.

Each branch has at most six500s slices, with at most two workers globally and one
BLAS thread per worker. Stage budgets are inherited: calibration90s, association60s,
regional finals20s/600iterations each, B7 stages90s/600iterations each; direct
qualification uses at most two rounds/100evaluations. Slice expiry is checked
between stages; it is not a hard process timeout. Reconstruction and actual stage
times are recorded. A claimed stage without a receipt is never silently retried.
There is no fallback endpoint: failures and exhaustion remain explicit. No claim
of embedded speed, independent validation or position improvement follows from
search scores. Position errors may be evaluated only after both branches seal.

`freeze.py` prepares metadata-only source/input bindings, original retained coarse
fits and bootstrap subsets. Run it only after review and authorization to freeze.
The runner verifies the complete inherited116 closure and bound input hashes,
reconstructs through its sanitized public corpus port, checks physical case identity,
and relies on105's exact native objective/full qualification checks before fitting.
Neither adapter nor discovery selection reads reference coordinates or errors.

After protocol publication, run one explicit slice using the production47e Python
environment, `PYTHONPATH=src:.`, and all three BLAS thread environment variables set
to1: `run.py native` or `run.py fixed`. Inspect the durable status before launching
another slice; never retry a failed or terminal branch automatically.
