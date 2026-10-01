# Conditional residual-scale prediction

At the accepted original baseline state for the first single of DS9/DS10/DS11, freeze satellite assignments and covariance. For each signal track, predict its contrasted residual under independent Student-t4 and under the shared Gamma(2,2) precision updated by every other track assigned to the same satellite in this scan. No fitting, geographic reference, model width search or group reselection.

For training group residual energy Q_T and dimension D_T, the posterior precision is Gamma(a,b), a=(4+D_T)/2, b=(4+Q_T)/2 (shape/rate). The held residual of dimension d and original covariance C has Student-t degrees of freedom2a and scale(b/a)C. Equivalently its log density is joint group log density minus training group log density. Verify both formulas. Singleton groups have no training data and must exactly match the independent control. Background tracks are excluded and counted.

Report every track's gain, pooled gain per contrast, median track gain per contrast on multi-track groups, and each group's total gain per contrast. Do not inflate support with singleton zeros. A positive conditional signal requires positive pooled and median multi-track gains on all three scans. The baseline state and identities already used the held observations: this is a conditional diagnostic, not independent predictive validation. It cannot override the previous failed localization expansion gate.

Tests cover posterior/joint-density equivalence, singleton equality and adverse prediction from incompatible training energy. Use sealed sources/inputs, shared lock, sequential single-thread cases and a90second cap each. No RF or localization fits. Preserve failures and no hyperparameter tuning.
