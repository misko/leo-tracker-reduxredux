# Detector margin and residual reliability: descriptive gate

Use the three metadata-selected first singles and their existing accepted one-start baseline states and labels. No fitting, GPS scoring, new RF, or quality-to-weight mapping is permitted in this diagnostic. Verify the quality overlay and the original input/source bindings.

Join each retained physical observation ID within its track to its candidate margin. Require exact normalized CFO and integer UTC consistency. Retain the existing independent-track and eight-point selection. Signal tracks receive median retained margin and contrast energy per dimension, Q/d = r' C^-1 r / d. Background tracks are counted separately, not assigned a satellite residual.

Hypothesis: larger median detector margin predicts lower residual energy. Report Spearman correlation, median Q/d above/below the fixed margin threshold 0.5, and concordance among pairs of tracks assigned to the same satellite. Concordance counts pairs with larger margin and smaller Q/d; ties are excluded and counted. Satellite grouping helps distinguish quality variation from orbit/association mismatch but does not eliminate confounding.

Directional gate for further investigation: negative Spearman correlation and greater than 50% within-satellite concordance in every dataset, with at least one comparable pair per dataset. This is an exploratory gate, not statistical significance or proof of a useful weighting model. Failure stops direct margin-to-variance fitting from these pilots. Report all tracks and exceptions; do not select a different threshold after inspection.

The fixed states and labels already used these data. These are in-sample residual diagnostics, not held-out predictive scores. A positive result would only justify a separate frozen held-block predictive experiment before any localization weighting changes. These three scans cannot establish transfer to pairs/quads or geographic generalization.
