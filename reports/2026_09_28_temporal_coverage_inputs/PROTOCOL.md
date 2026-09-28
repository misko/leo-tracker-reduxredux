# Frozen temporal-coverage input preparation

Use the 24 sessions selected by timestamps in the published covariance-refinement
coverage proposal: eight per DS7/DS8/DS9, spanning each dataset's endpoints.
No substitutions based on cache availability, analysis outcomes or location.
Keep the published first-eight panels as the fixed-budget comparison.

Reuse ten available inputs only after exact artifact-hash and loader checks:
eight DS7 records plus the first DS8/DS9 record. Archive previously unpublished
DS7 banks from the local cache so subsequent runs have repo-owned input paths.
For the other14 sessions export existing cached frequency tracks through the
unchanged public input ports and generate the unchanged corrected-DS6 causal
full-catalogue five-anchor/top8-union banks. No IQ reads or RF collection.

Bind dataset membership/capture manifests, partition seed2026092711, sample
rate, observation bytes, provider snapshots before capture start minus505s,
bank shapes/timing grid and eligible-track accounting through the existing
baseline loader. For DS9 also check the minted GLRT metrics-manifest binding.
Archive export environment and relevant installed public-reader source bytes.

At most two dataset workers. Each runs its records sequentially, with per-stage
caps: observations60s, banks240s, validation30s; address space4GiB, BLAS1,
nice19. Each worker has an1800s deadline. No automatic retries. Preserve failed
or pending stages and retain all24 requested sessions in the final ledger.
Do not fit an incomplete panel or silently drop a failed record. This report
prepares inputs; geographic fitting is a separate experiment after validation.
