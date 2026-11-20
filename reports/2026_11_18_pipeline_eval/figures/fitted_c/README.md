# Position error by receiver modification · Fitted calibration

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
