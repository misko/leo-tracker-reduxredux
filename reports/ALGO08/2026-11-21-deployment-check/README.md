# ALGO08 on the two newest sealed Gauss fast scans

At 8:06 a.m. Pacific on November 21, 2026, the two most recent completed recordings were the 7:24 and 7:40 a.m. lower-edge scans. Both contained 6,773 durable visits across the two receivers. The 8:05 a.m. capture was still recording at selection.

| Recording, Pacific | Visits admitted | Capture-quality exclusions | Fitted position error | Fixed-zero position error |
|---|---:|---:|---:|---:|
| [7:24 a.m. · live scan](http://gauss:8090/?scan_kind=fast&scan_id=fast8-auto-20261121-152419-0de49956-1-lower) | 6,743 | 30 | 707 m | 726 m |
| [7:40 a.m. · live scan](http://gauss:8090/?scan_kind=fast&scan_id=fast8-auto-20261121-154007-7e736acf-1-lower) | 6,747 | 26 | 479 m | 429 m |

Position error is horizontal distance to the evaluation-only Gauss roof reference. The watcher selected `algo08-two-scan-compact-v5-v1` as its default. The deployed launcher, detector and solver source, API reader modules and four pinned scientific assets matched the release. The live web service served the HTML and JavaScript from that same installation.

Both recordings were brought forward in the queue using the deployed worker's normal processing entry point. The 7:40 recording was also replayed independently from sealed NVMe storage while the RAID archive was copying it. The scheduled transfer timed out. A recording-specific retry with the existing archive tool verified all 8,218,914,455 bytes. Replaying the permanent copy produced byte-identical detections and the same terminal receipt, including both position estimates.

Chromium decoded all eight images on each normal Gauss scan page. All 16 responses were PNGs with the exact byte count, SHA-256 digest and dimensions recorded in the verification file. The eight images from the independent 7:40 replay also matched their production counterparts byte for byte. The links below open the original files served by Gauss. [Verification data](verification.json)

| Web diagnostic | 7:24 a.m. | 7:40 a.m. |
|---|---|---|
| Fitted and fixed-zero position maps | [PNG](0724/position.png) | [PNG](0740/position.png) |
| Detections and orbits · channels 1–4 | [PNG](0724/ch1-4-all.png) | [PNG](0740/ch1-4-all.png) |
| Detections and orbits · channels 5–8 | [PNG](0724/ch5-8-all.png) | [PNG](0740/ch5-8-all.png) |
| Unassociated detections · channels 1–4 | [PNG](0724/ch1-4-unassociated.png) | [PNG](0740/ch1-4-unassociated.png) |
| Unassociated detections · channels 5–8 | [PNG](0724/ch5-8-unassociated.png) | [PNG](0740/ch5-8-unassociated.png) |
| Frequency residuals · channels 1–4 | [PNG](0724/ch1-4-residuals.png) | [PNG](0740/ch1-4-residuals.png) |
| Frequency residuals · channels 5–8 | [PNG](0724/ch5-8-residuals.png) | [PNG](0740/ch5-8-residuals.png) |
| Frequency RMS per associated track | [PNG](0724/track-rms.png) | [PNG](0740/track-rms.png) |
