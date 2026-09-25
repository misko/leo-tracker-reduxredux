# Reconstructing five strong GLRT tracks from PSS

## Result

Four of five GLRT-selected tracks produced an independently associated PSS
frame-timing track.  On those four reconstructions, PSS recovered 134 of 168
GLRT support visits (79.8%).  Across all five attempted tracks, including the
failed reconstruction, recovery was 134/252 visits (53.2%).

The recovered PSS timing tracks are tight: their median timing-fit RMS is
0.065 microseconds.  After the PSS carrier series is branch-unwrapped using
only its own temporal continuity and one constant offset is aligned for
comparison, the median across-track pointwise median absolute CFO difference
is 6.261 kHz.

Separate robust linear CFO-rate fits have the same sign for all four recovered
tracks.  Their median absolute PSS-minus-GLRT rate difference is 0.524 kHz/s.
This is materially more encouraging than the earlier six-block PSS rate study,
but remains experimental because PSS carrier sidelobe branches and occasional
branch outliers are visible in two tracks.

| rank | path | GLRT support | best PSS track | PSS timing RMS | median absolute CFO difference | GLRT rate | PSS rate | rate difference |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | CH4 upper RX0 | 84 / 42.424 s | none | -- | -- | -- | -- | -- |
| 2 | CH1 upper RX0 | 52 / 28.593 s | 34 / 19.046 s | 0.039 us | 4.474 kHz | -3.777 kHz/s | -3.573 kHz/s | +0.203 kHz/s |
| 3 | CH2 upper RX0 | 52 / 25.323 s | 42 / 21.973 s | 0.250 us | 7.819 kHz | -3.817 kHz/s | -2.900 kHz/s | +0.918 kHz/s |
| 4 | CH1 upper RX0 | 36 / 16.185 s | 33 / 14.943 s | 0.048 us | 5.677 kHz | -3.573 kHz/s | -4.205 kHz/s | -0.632 kHz/s |
| 5 | CH4 upper RX0 | 28 / 14.585 s | 25 / 11.940 s | 0.082 us | 6.846 kHz | -4.102 kHz/s | -3.686 kHz/s | +0.416 kHz/s |

Track 1 contains 125 qualified isolated PSS modes on its 84 support visits, but
none formed a track satisfying the declared minimum of six blocks over two
seconds with at most 2 microseconds timing residual and at most 150 kHz coarse
CFO deviation.  This is not a statement that PSS is absent.  It says the very
long CFO-only GLRT association was not reproduced as one PSS timing corridor
under the frozen association policy.

## Selection

The frozen source is `scan-fw-d6704a759a9ec176`, a continuous dual-receiver
10 MS/s scan.  The five tracks were chosen before PSS evaluation as the top
five GLRT trajectory-family representatives, ranked by:

1. observation count;
2. time span;
3. GLRT trajectory residual RMS; and
4. deterministic trajectory identity.

This produces tracks with 84, 52, 52, 36, and 28 GLRT observations.  All five
are RX0 upper-edge tracks because those were the strongest representatives in
this recording; PSS did not influence that outcome.

## Reconstruction method

For every visit already assigned to one selected GLRT track, the replay runs a
blind PSS search from -1.2 to +1.2 MHz in 200 kHz steps.  Unlike the earlier
same-visit comparison, no GLRT epoch gate is used.  Qualified PSS modes are
associated solely through their circular 750 Hz frame phase and coarse CFO.

A PSS timing track requires:

- at least six distinct visit blocks;
- at least two seconds of support;
- no more than 2 microseconds maximum circular timing residual; and
- no more than 150 kHz coarse-CFO deviation inside one association.

When several PSS timing tracks exist within one GLRT support set, the primary
reconstruction is chosen by PSS point count, then span, then timing residual.
The counts of independently associated PSS tracks for GLRT ranks 2--5 are 5,
3, 2, and 1 respectively.  This fragmentation is itself evidence: a CFO-only
GLRT association does not necessarily correspond one-to-one with a PSS timing
corridor.

Only after the PSS timing track is frozen is its carrier estimate refined over
+/-120 kHz in 2 kHz steps.  The 113.636 kHz PSS sidelobe branch is lifted using
a rolling prediction from the PSS series itself.  A single constant CFO offset
is then aligned to GLRT for pointwise plotting; that constant has no effect on
the separately fitted CFO rate.  Both PSS and GLRT rates use MAD-scaled Huber
linear fits on exactly the matched PSS support.

## Interpretation

The experiment supports PSS as more than an isolated timing check: in four
cases it reconstructs a multi-second frame-timing corridor on visits selected
by a GLRT track.  Three tracks have timing RMS below 0.1 microseconds and the
fourth remains below 0.3 microseconds.

Carrier reconstruction is less clean.  Tracks 2 and 5 visually follow GLRT
well.  Tracks 3 and 4 contain PSS branch outliers; their pointwise RMSE values
(17.778 and 32.978 kHz) are therefore much worse than their median absolute
differences.  Robust rate fits retain the correct sign, but these outliers are
why the result should not yet replace known-pilot GLRT Doppler.

The tracks remain signal trajectories, not satellite identities.  The source
visits were selected from GLRT support, and neither method isolates spacecraft
Doppler from receiver, LNB, oscillator, or sample-clock effects.

## Artifacts

- `figures/2026_09_25_five_glrt_tracks_pss/five-track-pss-reconstruction.png`
- `figures/2026_09_25_five_glrt_tracks_pss/paired-track-points.csv`
- `figures/2026_09_25_five_glrt_tracks_pss/summary.json`
- `figures/2026_09_25_five_glrt_tracks_pss/reconstruct.py`
