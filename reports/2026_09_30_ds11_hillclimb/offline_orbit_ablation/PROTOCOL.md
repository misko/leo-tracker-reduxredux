# Offline orbit-state / identity mechanism ablation

Use only previously selected original scans22/23. Freeze each track's physical
satellite label to its training MAP at the sealed original or offline full-mixture
endpoint. These labels are inferred, not authenticated. Retain every track,
including labels that had low confidence, and preserve original catalogue
normalizers, observations, masks, time grids, CFO profiles and position bounds.

Fit all four combinations of original/offline orbit states and original/offline
fixed labels. Use original IID coordinates and configured center/timing0 as two
fixed starts for each combination: sixteen fits total. Keep the full-mixture
results as separate references; fixed-label likelihoods are different models.
Select the highest qualified training score before geographic scoring. Same
qualification gates as the parent pilot: optimizer success, margin>=.001,
gradient<=.01, finite-difference discrepancy<=.02. Preserve failed outputs and
all attempts. A crossed original-state/offline-label arm is still offline-assisted.

Report all cells and changes, not a winning cell selected by reference error.
This ablation can distinguish dependence on updated curves from dependence on
label changes within this local experiment; it cannot establish true identities,
an attainable causal estimator, a global optimum or an error floor.

Each child<=90seconds; at most three single-thread workers. No collection,
reference-based tuning, candidate search expansion or causal production change.
