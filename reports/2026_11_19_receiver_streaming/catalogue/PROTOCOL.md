# Orbital element checksum

Change only the computation of the standard mod-10 checksum on the first 68 characters of an orbital element line. Sum the digit values and count minus signs using a byte lookup on ASCII text. Preserve the original treatment of Unicode and malformed text. Keep every archive integrity check, causal catalogue choice, observation, satellite assignment, numerical stage and calibration setting.

Use the two preselected full-recording smoke cases DS26-0036 and DS29-0082. Compare fresh no-repair v5 inference with the four frozen roof controls on those recording IDs. Require the same position coordinates and frequency-fit statistics as the full numerical no-repair result in each calibration arm. The numerical worker starts from archived GLRT detections.

For the component timing, use a complete causal input catalogue for each case, retain all its element lines in order, and compare both checksums on every line before timing. Run five alternating paired passes on one pinned CPU in each case. Report checksum time separately from the inference wall time. Partial timing does not establish IQ-to-position latency.
