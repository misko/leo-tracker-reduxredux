# Independent noise-control review

No blocking implementation or score-algebra error was found. The review changed no noise files and ran no scientific fits or model tuning.

All 24 cases and 72 saved folds passed independent partition and score checks: every nominated family is held out exactly once, training/test groups are disjoint, saved training-point counts match pooled and receiver-law metadata, qualification reproduces, all applied noise SDs lie in 40–600 Hz, and maximum fold-gain replay discrepancy is 0. There are 67/72 positive fold gains.

The score uses z = Qᵀy and C = Qᵀdiag(v)Q for an orthonormal complement of the frozen polynomial design. Its zᵀC⁻¹z + log det C is the correct Gaussian contrast score; the omitted d log(2π) is identical between models. An independent heteroscedastic direct-solve/logdet check agrees with Cholesky to numerical precision. Constant, polynomial-offset and partition tests supplied with the model also pass.

The variance-law fitting path receives training pieces only. The adapter copies the scan and noise metadata, forces experimental per-ID values, and checks their application to both curved and predictive rows. The synthetic BIC selector flag is explicitly labeled; it is not presented as a measured BIC. No GPS, fitted position or orbital residual enters numerical noise fitting.

Publication scope qualifications:

- Heldout validation is conditional on the frozen graph: Curvature screening, piece membership/degrees and nominated-family grouping were determined from the complete frozen graph. Their selection is not retrained inside folds. The protocol already discloses this, so claims should remain a conditional noise-law comparison rather than independent pipeline/noise-truth validation.
- Whole-family holdouts do not establish time-block transfer: The seeded folds group nominated families and unmatched tracks, not time blocks. Shared receiver disturbances can span held families at the same times; unknown shared emitters can also be undergrouped. This is not a flaw in the stated family-only protocol, but the result should not be presented as randomized time-block or temporal-transfer validation.
- Training noise fit is a plug-in surrogate: Leverage-corrected residual squares are correlated and mix neighboring variances under heteroscedasticity. The inherited fit_variance optimizer profiles an unclipped law, while learn/variance score and apply its clipped version. Thus the training BIC quantity is a selection heuristic, not an exact likelihood/BIC for independent raw errors. The heldout full-contrast covariance and its determinant are algebraically correct and protect the stated model comparison.
- Predictive-point noise transfer is not separately validated: Noise laws are estimated and cross-validated on curved graph pieces, then applied by receiver/margin to predictive-only points as well. This matches the inherited plug-in architecture but does not independently establish those points' true frequency-error variance.

These qualifications limit interpretation; they do not invalidate the frozen-graph family-heldout comparison or its sealed matched-position evaluation. Better contrast density alone does not establish improved location accuracy.
