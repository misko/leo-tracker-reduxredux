# Frame-level frequency abstention using wrong-pilot controls

Frozen before execution. Keep all eight visits, both RXs and 80 frames from the
existing pilot-matrix replay. Verify source and cache hashes from the peak study.
Every frequency search uses pilots 22–221; pilots 222–301 score predictions.

For each visit/RX, derive a threshold from the maximum explained-energy score
of 90 wrong-template searches: three fixed symbol rolls (17, 41, 83), each on
the first 30 frames. Use the same six-peak search/refinement as the exact arm.
Freeze the threshold before scoring the remaining 50 frames. The maximum is
an empirical control envelope, not a calibrated false-alarm probability.

If an exact frame exceeds the envelope, retain its best frequency and prediction;
otherwise mark its frequency unavailable and predict zero coherent mean. Compare
with unconditional exact prediction on every evaluation frame: abstentions have
NMSE one and are not removed. Evaluate a rolled-17 template on the held frame
population as a control acceptance diagnostic. Also report the unchanged frozen
0.2 gate from the preceding study to quantify avoidable coverage loss.

No new IQ, geographic fit, runtime change or detector qualification. Inspect the
production noncoherent GLRT before claiming these framewise problems apply to it.
This is a research observable-quality model; production does not necessarily emit
one frequency observation for every frame in these diagnostic caches.
