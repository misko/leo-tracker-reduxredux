# Is the position solve sensitive to the historical sky-screening center?

The deployed DS30 station offer supplies a 25 km search square centered at 37.906°, −122.545° and a separate sky-screening center of 37.5°, −122°. The published simulations ordinarily screen at the search-square center. A field installation can legitimately supply only a search square. This test checks whether removing the historical station setting changes the solution while holding its I/Q, search bounds and orbital archive fixed. The distinct screening center is operator-supplied input.

## Prespecified comparisons

Use the saved native detections from the complete frozen conditional receiver trials. On DS30-0016, replace the historical screening center with the offered square's center. On the public northern near-edge simulation, move only the screening center two square widths east and two widths south in the solver's local coordinate frame. Each original result has a complete paired publication on disk. Both altered offers reuse the original capture-time orbit archive, detector measurements, two calibration fits, fit policy, and grid budget. Score changes in endpoints and RF residuals separately after running the solver. Retain any failures in the comparison. This experiment does not change deployment, time the receiver or use a fresh confirmation location. [Original paired results](receiver-residual-prefix-192.md)

## Results

| Saved input | Screening-center displacement | Fixed-zero / fitted endpoint movement | Fitted horizontal error, original → changed | Fitted RF RMS, original → changed |
|---|---:|---:|---:|---:|
| DS30-0016, historical offset removed | 65.86 km | 2.59 / 2.75 m | 1.66144 → 1.65905 km | 109.47894 → 109.47917 Hz |
| Northern simulation, offset added | 70.89 km | 0.136 / 0.071 m | 0.14078 → 0.14083 km | 5.16663 → 5.16673 Hz |

The unchanged controls reproduced both complete publications' coordinates and terminal RF residuals exactly. Both altered offers yielded fixes and preserved the satellite-owner digest for each calibration arm. Fixed-zero horizontal errors were 1.64367 → 1.64163 km on DS30 and 0.10569 → 0.10565 km on the northern simulation. The site's historical screening center had little effect on this physical recording. This test displaced the sky-screening calculation while keeping the search square fixed. A distant incorrect search square still causes a false fix in the unguarded solver. [Four complete saved-solver receipts](measurements/conditional-screen-center.json.gz) · [Search-region evidence](geographic-input-audit.md)

Run `solver_gc_trial.py --defer-preparation --composed-tle-parser LIBRARY SHA256 NATIVE ARCHIVE ASSETS REGION NATIVE_SHA256` on each original and changed offer. Use the native outputs and verified archives in the DS30-0016 reverse-order and northern conditional receipts. The four receipts above bind the full offers and native file hashes. [Physical input](measurements/DS30-0016-conditional-reverse.json) · [Northern input](measurements/north-edge-conditional.json)
