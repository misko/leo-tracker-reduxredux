# DS7 frozen temporal-transfer solver

This directory contains the unscored chronological group-eleven transfer panel
declared in `TRANSFER-SPEC.md`. It uses the unchanged wave-two exact baseline
arm and science configuration. No score, pose, or reference artifact was read.

All eight independent units (`single-081` through `single-088`) converged
without boundary hits. Their elapsed adapter times ranged from 16.71 to 25.78
seconds. The joint `group8-11` fit also converged without a boundary hit in
165.02 seconds, with 62 total objective/gradient evaluations, 484 eligible
tracks, one declared mask-policy exclusion, and training RF RMS of 473.02 Hz.

The progressive immutable-input workflow reused every completed single and did
not duplicate a fit. Total adapter use was 329.476 of the authorized 900
seconds. Every run used explicit unit selectors, CPU1/BLAS1, nice 19, and a
300-second per-unit cap.

`scan-estimates-group11/` contains the eight independent estimates. Each
artifact binds its source request, response, and run seal. The all-88-accounted
control input index is `scan-estimate-index-group11-v1.json`; exactly the eight
group-eleven rows are ready and the other 80 are explicitly unavailable.

