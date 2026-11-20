# Position error by receiver modification · Zero calibration

The top row counts every recording. A curve that ends at 50% means the receiver returned positions on half the recordings. Each dot below is one returned position. The diamond marks their median. A forced estimate is the receiver’s best guess even when it withheld a fix.

[PDF](modifications.pdf) · [Per-recording errors](modifications.csv) · [Fix counts and both calibration settings](../README.md)

## V5 without evidence rendering

DS26 extracts coordinates from the archived numerical fits. DS29 reruns the full fit from detector outputs.

![V5 without evidence rendering](v5_lean.png)

## Batched pilot-bank GLRT

Batched Python GLRT, tracking and position search on 80 windows per recording.

![Batched pilot-bank GLRT](glrt_batch.png)

## Streamed IQ decoding

The streamed reader supplies the same 80 windows to the native GLRT, tracker and solver used for bounded raw-IQ replay.

![Streamed IQ decoding](iq_stream.png)

## Early screening in the pilot-bank GLRT

Screened Python GLRT, then tracking and position search on 80 windows per recording.

![Early screening in the pilot-bank GLRT](glrt_cascade.png)

## Reusing orbital states

Reuse orbital states across the original single-tile and four-tile searches.

![Reusing orbital states](orbit_interp.png)

## Horizon screening for Doppler scoring

Screen below-horizon satellites before fitting the measured Doppler tracks.

![Horizon screening for Doppler scoring](shape_score.png)

## Compressing Doppler tracks

Compress the measured Doppler tracks before single-tile and four-tile search.

![Compressing Doppler tracks](track_reduce.png)

## Causal track linking

Link native GLRT peaks with a causal tracker, then run the regional solver.

![Causal track linking](track_link.png)

## Position from bounded raw-IQ replay

Native GLRT, tracking and position search on 80 IQ windows per recording.

![Position from bounded raw-IQ replay](iq_position.png)

## Fitting position with per-track offsets removed

Remove per-track frequency offsets before estimating receiver position.

![Fitting position with per-track offsets removed](projected_fit.png)

## Full ordinary native GLRT with the v5 solver

All eligible IQ windows on both physical inputs, followed by the full numerical v5 fit. The six preselected timing recordings use their original clock and capture exclusions.

![Full ordinary native GLRT with the v5 solver](native-to-v5.png)

## V5 stopped after the initial satellite assignment

Position extracted at this stage of the original v5 run on 127 DS26 and eight DS29 recordings.

![V5 stopped after the initial satellite assignment](v5_stop_initial.png)

## V5 stopped after the conservative refit

Position extracted at this stage of the original v5 run on 127 DS26 and eight DS29 recordings.

![V5 stopped after the conservative refit](v5_stop_conservative.png)

## V5 stopped after the satellite-family refit

Position extracted at this stage of the original v5 run on 127 DS26 and eight DS29 recordings.

![V5 stopped after the satellite-family refit](v5_stop_family.png)

## V5 stopped after the signed orbit correction

Position extracted at this stage of the original v5 run on 127 DS26 and eight DS29 recordings.

![V5 stopped after the signed orbit correction](v5_stop_signed.png)

## V5 stopped after the cavity fit

Position extracted at this stage of the original v5 run on 127 DS26 and eight DS29 recordings.

![V5 stopped after the cavity fit](v5_stop_cavity.png)

## Reduced v5 through the cavity fit

Fresh execution from native detections on the six paired timing recordings.

![Reduced v5 through the cavity fit](v5_core.png)

## Doppler fit with shared receiver and satellite corrections

Shared receiver clocks and satellite timing corrections on the original one- and four-region offers.

![Doppler fit with shared receiver and satellite corrections](shared_doppler.png)

## Accelerated pilot acquisition with the v5 position fit

16 scheduled IQ windows per recording use the accelerated detector. Remaining detections come from the archive. Both v5 fits rerun.

![Accelerated pilot acquisition with the v5 position fit](anchor_receiver.png)

## V5 using all visits to odd RF channels

Keep all visits to RF channels 1, 3, 5 and 7. Rebuild tracks and fit both v5 positions through the cavity stage.

![V5 using all visits to odd RF channels](glrt_odd_channels.png)

## V5 using all visits to even RF channels

Keep all visits to RF channels 2, 4, 6 and 8. Rebuild tracks and fit both v5 positions through the cavity stage.

![V5 using all visits to even RF channels](glrt_even_channels.png)

## V5 with compact orbital projection

All eight channels, from archived native detections to a fresh v5 cavity fit. Project Doppler directly from the causal orbit knots.

![V5 with compact orbital projection](orbit_projector.png)

## Streaming Doppler tracker

Causal tracks and scan-end fixes from saved detector candidates. The replay starts after waveform detection.

![Streaming Doppler tracker](early_stream.png)

## Guided pilot search with blind reacquisition

Full-scan fixes replay saved detector candidates with pilot gates and blind scouting. The raw-IQ cross-check used a separate sample of short windows.

![Guided pilot search with blind reacquisition](early_pilots.png)

## Satellite-family consensus

A robust vote across satellite families uses archived Doppler tracks and causal orbits.

![Satellite-family consensus](early_consensus.png)

## Packed Doppler orbit table

A packed orbit table and continuous position fit use archived Doppler tracks.

![Packed Doppler orbit table](early_compact.png)

## Stationary site forecast from prior fixes

A median of earlier completed fixes forecasts position at scan start. The forecast uses zero current-scan radio samples and assumes the receiver stays put.

![Stationary site forecast from prior fixes](early_stationary.png)

## 12 tracks chosen by geometry

The position fit uses 12 archived Doppler tracks selected for horizontal geometry.

![12 tracks chosen by geometry](early_coreset.png)

## Doppler changes only

The position fit uses paired frequency changes from archived Doppler tracks. Both calibration arms produce the same positions.

![Doppler changes only](early_differences.png)

## Marginalized position grid

A coarse-to-fine position grid uses archived Doppler tracks and compares competing satellite identities.

![Marginalized position grid](early_grid.png)

## Pass-event timing only

Event times come from saved detector output. Ambiguity checks withheld all eight fixes.

![Pass-event timing only](early_events.png)

## Tiny coordinate network

A network trained on synthetic examples predicts position from a Doppler map built from archived tracks. Both calibration arms produce the same positions.

![Tiny coordinate network](early_network.png)

## Observe alternate complete eight-channel sweeps

Observe alternate complete eight-channel sweeps. Rebuild the tracks and fit both positions using the same orbital search and cavity solver.

![Observe alternate complete eight-channel sweeps](sweep_schedule.png)

## Verify satellite assignments on later Doppler samples

Fit the first two thirds of each measured Doppler track. Test its remaining samples before publishing a position on the original one- and four-region offers.

![Verify satellite assignments on later Doppler samples](arc_validation.png)

## Compact v5 with the final position repairs

Full-channel detections, compact orbital projection and final v5 repairs. Two smoke recordings plus two DS26 cases selected to exercise different repairs.

![Compact v5 with the final position repairs](compact_finish.png)

## Full v5 with bytewise orbital element checksums

Replace the orbital element checksum inside a fresh full numerical v5 fit. Both recordings start from capture-era detector output.

![Full v5 with bytewise orbital element checksums](catalogue_checksum.png)

## Reorder the pilot correlation sums before the v5 fit

Eight scheduled IQ windows per recording use the modified pilot detector. The remaining detections come from the archive. The compact v5 cavity solver runs again.

![Reorder the pilot correlation sums before the v5 fit](pilot_kernel.png)

## Native wideband pilot acquisition on 20 ms visits

Two 20 ms IQ windows per recording were tested with the wideband native detector. This trial measured its detector outputs and CPU time only.

![Native wideband pilot acquisition on 20 ms visits](native_geometry.png)

## Native fractional winner gate with the v5 solver

Apply the fixed 0.060 gate to fractional candidates from the six complete ordinary native factor sets, then rerun the full numerical v5 fit.

![Native fractional winner gate with the v5 solver](native_winner.png)

## Full raw replay through one physical receiver input

Replay all eligible IQ windows through a detector context with only the physical RX0 input, then run the full numerical v5 fit. The source archive contains both lanes.

![Full raw replay through one physical receiver input](single_rx0.png)

## RX0 position from two archived detector sources

Keep the RX0 slot in two complete archived factor sets per recording, one capture-era and one ordinary native. Run full numerical v5 on each source separately.

![RX0 position from two archived detector sources](single_rx0_factors.png)

## Late pilot confirmation at the proposed epoch and CFO

Measure late pilot evidence on sampled IQ visits after ordinary fractional GLRT. The detector gate did not advance to position fitting.

![Late pilot confirmation at the proposed epoch and CFO](pilot_confirmation.png)

## Shared sliding tones for coarse pilot acquisition

Measure a shared sliding-tone coarse search on fixed samples of authenticated IQ visits.

![Shared sliding tones for coarse pilot acquisition](spectral_grid.png)

## Longitude controls on Doppler arc predictions

Longitude controls on the eight DS29 blind-panel recordings with the correct region among four offers. This trial did not test DS26 or single-region queries.

![Longitude controls on Doppler arc predictions](off_region_test.png)
