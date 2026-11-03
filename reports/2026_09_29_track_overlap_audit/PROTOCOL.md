# Measurement reuse and overlapping frequency histories

Audit every track in the existing 24-scan pool of each of DS7, DS8 and DS9 (72 scans total). No reference coordinate, fitted position or candidate label enters selection.

For exact-key reuse, group observations by scan, receiver ID, exact RF metadata, time rounded to 1 ns and measured frequency rounded to 1 microhertz. Count keys repeated across distinct tracks, excess cross-track copies and keys appearing in both training and held observations. Also count repeated timestamp keys inside a single track. Quantization is explicitly part of the key; these are equality diagnostics, not proof of shared raw-IQ provenance.

For a separate similarity diagnostic, compare every pair of tracks with the same scan/receiver/RF and at least eight coincident training timestamps spanning at least one second. Use only matched timestamps. Remove the mean frequency difference and report RMS difference; flag <=10 Hz (one tenth of the existing 100 Hz likelihood scale). Also report RMS after removing a linear difference. A similar frequency history may be real common-satellite motion across distinct measurements; do not automatically classify it as duplicate data.

These fixed thresholds are diagnostics, not fit-selection criteria. Retain all eligible pairs and all scans; no weights change. No fitting, reference evaluation, new RF, or production changes. Per-dataset process cap 120 seconds, BLAS1.
