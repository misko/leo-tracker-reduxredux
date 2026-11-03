# Deterministic duplicate-observation sensitivity

Use all 24 scans per DS7/DS8/DS9, preserving original files. The repeated-key definition is the preceding overlap audit: scan/receiver/exact RF, timestamp rounded to 1 ns, measured frequency rounded to 1 microhertz. Retain each key in the lexicographically smallest track ID. Preserve the surviving observation's training/held label. Slice observations and candidate-state arrays together. Require at least two training and one held observations in every track after removal; do not silently drop a track if this fails.

Require removal counts and training/held counts to match the independently saved overlap audit. Reconstruct the unchanged q=0.2 mixture on deduplicated in-memory documents. Start one local refit from each dataset's previously qualified N24 endpoint, with original optimizer and audit gates. This is a local sensitivity experiment, not a new global optimization campaign. Preserve failures; no retry or substitution.

Primary outputs: position displacement from the original endpoint, reference-distance change, training-score/gradient change at the original endpoint, and held change between old and new parameters on the SAME deduplicated observations. Also evaluate parameter changes on unchanged original observations. Never subtract likelihoods on different observation dimensions and call it a model improvement.

No input, production or golden-fixture mutation; no RF collection. Per-dataset subprocess cap 120 s, BLAS1. No reference-dependent owner selection or optimization.
