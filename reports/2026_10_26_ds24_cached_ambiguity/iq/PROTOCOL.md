# Small pilot-only detector-selection control

This is a synthetic numerical control, not a new recording or a faithful full
Starlink channel simulator. It uses the historical deployed detector that
exactly reproduced one original DS24-0011 window in the previous iteration.
That original replay is not repeated and no recorded IQ is read here.

Generate continuous-time eight-tone edge-pilot signals from the repository's
immutable Appendix-A state fixture, sampled at 10 MS/s. Decode the fixture
directly and synthesize every sample using the exact 750 Hz frame period,
4.4 microsecond symbol period and fractional frame epoch. Do not copy and
round repeated detector-template frames. Check the first integral-epoch frame
against the deployed template as a construction check; this shared pilot law
does not independently validate the physical waveform. Omit unknown payload,
analog filtering, multipath, hardware drift and satellite geometry explicitly.

Use 20 ms, two receivers, upper-band mapping from the already verified first
DS24-0011 target. Call the deployed public production_glrt numerical port with
synthetic samples and only the frequency-mapping fields it needs. Do not make
a provider-attested captured-window contract for synthetic data. Retain all
returned candidates, fractional statuses and margins with the original .025
gate and maximum-eight-candidate policy. No detector tuning.

Eight scenarios are fixed before any detector call, each with seeds 20261026
and 20261027 and independent noise on the two receiver columns:

1. Noise only.
2. One strong source: CFO 100000 Hz, amplitude 1000, epoch 127.25 samples.
3. One weak source: same CFO/epoch, amplitude 75.
4. Two coincident-epoch sources, CFO 100000/100500 Hz, amplitudes 1000/600.
5. Two coincident-epoch sources, CFO 100000/103000 Hz, amplitudes 1000/600.
6. Two separated-epoch sources, CFO 100000/100500 Hz, epochs 127.25/811.75.
7. Two separated-epoch sources, CFO 100000/103000 Hz, epochs 127.25/811.75.
8. One strong source with CFO 100000 Hz at window start and rate 10000 Hz/s.

Source initial phases are .3 and -.8 radians. Complex Gaussian noise has RMS
300 ADC units; use the same noise realization within each seed/receiver across
scenarios. Round once to signed-16 IQ and require no clipping; report actual
signal/noise powers. Every synthetic input and output is hashed; IQ arrays are
not published. All 16 paired-window slots remain, including failures.

Compare the actually highest-margin accepted candidate with the nearest known
CFO and also report all returned candidates near each injected epoch (circular
frame distance <=3 samples). No oracle choice replaces the detector's choice.
Coincident-epoch sources are explicitly ambiguous; a nearest-source distance
is not correct identity recovery. For the chirp, give difference from midpoint
CFO (100100 Hz) and the instantaneous CFO range, without treating a fitted
constant's pivot discrepancy as an established bias. Four noise draws per
scenario do not establish a population bias or false-alarm rate.

Freeze source and fixture/deployment hashes after owned construction/reporting
tests and an independent scope preflight. Then one sequential invocation, at
most 120 s wall time including imports/synthesis/detector calls, one BLAS
thread, no retry or post-outcome parameter changes. Stop an individual call at
20 s, retain missing slots. The result concerns detection/selection in this
idealized control only: no graph tracks, satellite associations or position
accuracy are measured. A later crossing-track or recorded-background experiment
needs its own justified protocol; do not infer it from this control.
