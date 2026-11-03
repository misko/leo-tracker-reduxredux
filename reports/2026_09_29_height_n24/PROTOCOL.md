# Pooled N24 fixed-height sensitivity

Repeat the N8 fixed-height sensitivity at 100 m and 300 m WGS84 ellipsoidal height using the saved DS7/DS8/DS9 N24 baselines. Heights are hypothetical sensitivity offsets, not surveyed values. Reuse the tested HeightStationary implementation, original candidate banks and observation masks. Require zero-height score replay and exact session order. Independently warm-start each fixed-height E/N/time refit from the saved zero-height solution; apply existing optimizer and finite-difference qualification. No height selection from reference error.

Record horizontal shift, horizontal reference distance, training and held changes, and candidate-visibility changes both at the starting endpoint and the final endpoint relative to zero height at the original fit. Report any support change explicitly. These are local sensitivity refits, not global optimization or an uncertainty bound. No RF collection or production changes.
