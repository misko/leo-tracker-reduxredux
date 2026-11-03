# DS11 known-pilot audit: complete coverage, mixed frequency estimators

All111 frozen training observations were extracted and measured successfully.
Every sampled IQ chunk passed the public reader's compressed and decoded
size/digest checks. Extraction took20.77seconds in one120-second process;
measurement took25.32seconds in one180-second process. Neither pilot arm hit
its frequency-search boundary. No row was replaced, filtered or retried.

The longer pilot fit improves within-excerpt held-symbol prediction on72/111
excerpts, with positive mean and median gains on both tracks. The shorter fit
improves only24/111 and worsens mean and median prediction on both tracks.
These are waveform prediction results, not position-error improvements.

| Track / arm | Improved excerpts | Mean NMSE gain | Median NMSE gain |
|---|---:|---:|---:|
|10.71GHz, short|15/65|-0.008032|-0.002837|
|10.71GHz, long|45/65|+0.001261|+0.000308|
|11.21GHz, short|9/46|-0.009380|-0.006890|
|11.21GHz, long|27/46|+0.000516|+0.000176|
|All, short|24/111|-0.008591|-0.003884|
|All, long|72/111|+0.000952|+0.000250|

Gain is cached-frequency NMSE minus corrected-frequency NMSE, averaged across
eight frames per excerpt. It is an absolute dimensionless NMSE difference,
not a relative percentage. Short fits use symbols2–65; long fits use22–221.
All arms calibrate frame/carrier gains on22–221 and evaluate222–301. The shared
frame and track structure limits any interpretation as independent trials.

The long-fit canonical corrections have median offsets9.254Hz and6.668Hz for
the10.71GHz and11.21GHz tracks. After subtracting those medians, their RMS
variations are33.247Hz and22.952Hz, respectively. Descriptive linear slopes
are-0.315Hz/s and+0.566Hz/s. Those slopes describe measured corrections; they
are not extra fitted nuisance parameters or calibrated physical drift terms.
Constant offsets alone are largely absorbed by the position model's per-track
CFO profiling, so separating offset and temporal shape matters.
No track-constant correction arm was evaluated at the waveform level; the
NMSE gains therefore cannot be attributed specifically to temporal variation.

A later [nominal support audit](../norad65512_position/support_audit.json)
finds that using the first eight frames places the long pilot's geometric
center typically4.279ms before the exported GLRT support center. The latter
uses valid GLRT symbols across the full20ms probe. The short pilot's typical
offset is4.667ms. These are nominal FFT-support centers, not measured effective
frequency-estimator weights. The waveform NMSE observations above remain
unchanged; positioning comparisons must account for this support difference.

The pilot covers111/1940 exported training rows in scan0, from the two tracks
selected by their previously measured source influence. Their NORAD65512
assignment remains conditional. All65 localization-held values in those tracks
are untouched; no positioning or geographic scoring occurs in this audit.

The manifest SHA256 is
`09dffab44efa6d2846c41e70a2e2a7b22ac5a7cf43ea58528dfa7ab992a1ebb5`.
Fourteen preparation/runner tests and two shape-summary tests pass. The
metadata-only preparation completes in23.94seconds. Independent source and
row verification checks all46 source bindings,111 training rows, exact aliases,
and the65 excluded localization-held rows. The separate chunk metadata audit
records389881727 compressed bytes and532800000 decoded bytes for the selected
visits; this is not a rehash of the entire recording.
An independent read-only audit also rehashes every excerpt and reproduces the
complete per-track and aggregate summary exactly.

The frozen inventory and protocol remain unchanged. Full measurements are in
`local/measurements.json`, source-bound descriptive statistics in
[measurement_summary.json](measurement_summary.json), and terminal evidence in
`attempts/`. A separate [matched positioning protocol](../norad65512_position/PROTOCOL.md)
carries **both** pilot arms forward with all111 corrections, without selecting
an arm from these held-symbol results. Any single-scan position change will
remain a mechanism test rather than a validated general DS11 improvement.
