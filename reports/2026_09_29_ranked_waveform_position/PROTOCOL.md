# Ranked waveform correction: frozen geographic test

Use exactly the72 observations in observation_influence/queue.json: eight per
panel. Do not replace failures or rank on waveform/held/geographic outcomes.
Bind each to original observation, public track and candidate; extract its20ms
probe using public read-only ports. At most four120second checkpointed extraction
invocations, one process/thread. No new RF collection.

On the first eight complete frames, fit one long-pilot residual from22–221,
using existing independent frame/carrier gains, corrected upconversion phase,
±1500Hz search and25Hz grid/refinement. Require two in-band carriers as before;
retain failures and boundary fits. Score222–301 for descriptive waveform evidence,
never for selection. Numerical cap120seconds. Failed excerpts leave their
original observations unchanged; report coverage rather than replacing them.

Convert each residual to canonical Hz with11.2e9/actual_rf_hz, preserving the
existing integer alias. Modify only these training observations in memory.
Keep every original track, candidate bank, mask, timing bound and held observation.
Use the same full q020 geographic model and three-start local fitting rules as
sparse_waveform_position: identical cached/corrected starts, train-only selection,
projected gradient<=.01 and independent gradient audit<=.02. Per-panel cap60s.

Compare all nine panels against the cached baseline and the previous eight-per-
panel correction budget. Report reference error, held scores on unchanged held
data, all starts/failures, correction magnitudes and position movement. Also
compare observed movement with summed local sensitivity predictions descriptively.
No threshold or model retuning after results. Reference and panels are inherited
and exposed; no independent accuracy claim, new-site validation or global optimum.
