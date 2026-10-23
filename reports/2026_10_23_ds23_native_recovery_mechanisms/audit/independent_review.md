# Independent mechanism and report review

Reviewed the final README against saved solver, exclusion, bias-prior and reporting evidence, with no additional fits. No blocking scientific or numerical discrepancy found in the reviewed claims.

## Verified findings

- Final grid arithmetic is 24 family/weight fits + 12 solver fits + 2 exact-path exclusion fits + 18 bias-prior fits = 56. Twelve final family/weight result jobs and twelve archived initial jobs exist. The disclosed 98 executions reconcile as 56 final + 24 ineffective initial family/weight executions + 18 repeated bias executions. The last total is execution-history accounting, not 98 distinct scientific settings; there is no separate per-execution ledger in the reporting receipt.
- The 0365 ordinary summary fails only `GRAPH_PATH_persistent5s_005/linear/lag1` in both arms. Constrained fits pass, with worsened common-mask objective and reported geographic error. Exact-path exclusion has two passing fits, retains parent IDs, and common complete-mask replay still fails the excluded gate. README correctly labels the ordinary full-mask endpoint ineligible and the exclusion a mechanism prototype.
- All 18 final bias-prior summary rows qualify. At 600 Hz relative to 300 Hz, control changes independently recompute to -18.0099/+28.6201 m on 0041 and +20.2523/+9.7073 m on 0272 (c0/fitted-c). The README's rounded values and statement of inconsistent control improvement are correct.
- All 23 files in `reporting/receipt.json` input hashes matched during review. This receipt protects the reported input banks; it is not by itself a full source/dependency manifest.
- Discovery and final scoring are distinguished correctly. Final predictive paths share one integrated calibration covariance. Original observation-ID disjointness was audited by the parent diagnostics. Identity probabilities concern the active family set and do not establish catalogue-wide identity.
- GPS errors are computed in reporting scripts. Reviewed fitting scripts do not use evaluation GPS to select a width, deletion or endpoint. The README keeps the published reference and promotes no model or prior. Mechanism development and proposed next rules remain explicitly same-site and diagnostic.

## Independent fixed-position numerical check

`audit/test_bias_actual.py` passed for DS23-0259 in both c arms. At each saved ordinary native position and saved phase reference, rebuilding the problem separately for 300 and mixed 300/600 Hz priors yields exactly identical curved calibration coefficient arrays and exactly identical curved objective. This is fixed-position invariance; nuisance coefficients at different optimized endpoints need not match.

The test independently constructs the dense covariance

`diag(2*sigma_measurement^2) + U C U.T + blockdiag(sd_entry^2 * 11.T)`.

Parent entries use 300 Hz, new entries 600 Hz. Its dense Gaussian score matches the modified implementation within 2e-5, and a cross-entry block is nonzero and agrees with `U_i C U_j.T`. The existing two bias tests also passed, including numerical equality of the constant-300 implementation with the original. No new fits were executed by this reviewer.

At the original saved native endpoints, the independent check produced total objectives 5425.797330823192 / 5435.787251383661 under 300 Hz and 5430.94758651544 / 5440.814745606678 under mixed 300/600 Hz (c0/fitted-c). These different-normalization scores are replay diagnostics, not cross-prior selection evidence.

## Reproducibility caveats

- Preserve and hash final scripts, protocols, summaries and tests in the publication manifest as well as upstream numerical dependencies. The earlier 786-file seal alone cannot identify newly written experiment/report code.
- The scripts bind outputs to their own directory and use absolute upstream banks; reproducing into a new artifact requires copying the capsule with its relative structure before running. A bare repository virtual environment lacks SciPy; `/tmp/algo03-feasible-deps` supplies the recorded scientific dependency.
- Problem objects cache calculations by position. After changing the globally configured predictive prior, rebuild the problem before evaluating the same position. The final bias script does this for its common-model snapshot; the independent dense test does so explicitly. Reusing an existing cached problem would conceal the changed prior.
- The 98-execution history is reconciled from disclosed reruns and saved final/initial jobs. Retain first bias-run logs or receipts if independent execution-by-execution reconstruction is desired.

Run the owned fixed-position test from the repository root with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/tmp/algo03-feasible-deps:src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider /srv/bulk/leo/research/algo04-native-mechanisms-20261023/audit/test_bias_actual.py`.
