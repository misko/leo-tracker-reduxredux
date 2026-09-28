# Pilot frequency transfer prerequisite

Use the first chronological recording from each frozen DS7/DS8/DS9 panel.
Select the earliest all-training and earliest all-held visits with both
receivers represented in the existing baseline export. Within each visit and
receiver select the lexicographically first acquisition candidate ID, using
the existing public trajectory projection and frozen graph rules. Do not
replace unavailable records/windows. Freeze candidate IDs, source intervals,
analysis identity, epoch/CFO basin and complete-visit IQ budget before reading IQ.
There is no temporal line fit or cross-channel frequency transfer in this test.

For every complete frame in each selected window, demodulate in its bound
acquisition basin and wipe the known even-Qin pilots. Fit ordinary and robust
profile CFO on Qin symbol indices 0 modulo 4; evaluate ordinary profiled
coherence on unused indices 2 modulo 4, compared with residual zero (the
acquisition baseline). The held score profiles tone gains for every method;
held symbols never determine frequency. Use ±2000 Hz, 100 Hz coarse and 5 Hz
fine steps, robust maximum four iterations. Retain boundaries/failures rather
than silently dropping them. One seeded symbol-varying QPSK scramble per frame
is evaluated at the unchanged training-derived frequencies as a negative control.

Additionally inject ±250 Hz phase ramps into the training pilot matrix and
refit. Compare recovered increments with known injections, retaining all rows
and boundary/expected-out-of-bounds status. This checks post-demodulation
frequency equivariance, not end-to-end IQ acquisition, absolute RF truth, an
independent emitter identity, clock calibration or position accuracy. It is
possible to pass equivariance while retaining a large frequency bias.

Freeze one deterministic seed per frame, 2026092800 + window_index*100 + frame_index.
Archive pilot matrices for numerical replay, with exact source bindings.
Report paired per-window means and counts, separately for each dataset/receiver;
frames are correlated and are not independent population samples. Aggregate
equally over windows, not by counting frames as independent replicates.

Three metadata-only preparations each have a 90-second cap. Three waveform
jobs each have a 120-second cap, 64 MiB returned complete-visit IQ limit,
256 MiB underlying unique uncompressed-chunk limit (public readers cache chunks), one
numerical thread, nice19 and 4 GiB address-space cap. Run sequentially. No
retries or replacements; terminal failures remain evidence. Public read-only
IQ ports only, no new RF, no geographic reference access, no baseline mutation.
This prerequisite cannot promote a geolocation model. Require positive held
coherence gains on each dataset, no estimator boundaries, and maximum absolute
in-bounds injected-shift error ≤5 Hz before planning a larger downstream
matched-input position ablation; report every failure of these gates.
