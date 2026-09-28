# Wave 4 input-integrity audit

The final frozen input has all 88 distinct plan sessions in plan order: 24 ready and 64 unavailable. All 72 artifacts attached to ready records hash exactly to their frozen digests. The 16 pre-existing ready rows are byte-for-byte equivalent JSON rows to the Wave 3 final input.

For each new session 009–016, the production-format observation eligibility rule (at least two training and one held observation) selected exactly the manifest track set. Every candidate bank has the canonical 41-point timing grid, its candidate counts agree with its manifest, and its position and velocity tensor shapes agree with the corresponding observation lengths. No missing or duplicate track binding was found.

The 267 Wave 3 closeout hash bindings remain unchanged when interpreted at their recorded roots: repository root for `source_files` and `reports/2026_09_27_ds7_wave3` for `wave_files`.

The preparation receipt distinguishes 589.885 seconds of outer-controller wall time from 567.297447 seconds summed from per-recording reports. Neither figure indicates a timeout.

Machine-readable details are in `INPUT-INTEGRITY.json`.
