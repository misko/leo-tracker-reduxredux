# Cached-tracking proposal scout

This bounded development experiment asks whether a cheap screen can route likely
pilot-bearing receiver-visits to expensive blind confirmation. It evaluates the
existing native six-window rank and one sparse CI16 screen. The sparse screen uses
5,000 pairs per window at an integral three-frame lag, normalizes each correlation,
and takes the root-mean-square magnitude across the six windows. This tolerates a
constant CFO phase at the lag but is not a proof of CFO invariance or signal identity.

Thresholds are the inclusive minimum over the 36 development reference positives.
This guarantees development retention by construction and is not a calibrated
classifier. A nonroute is `measured-screen-negative`, never confirmed absence or
noise. The 5 MS/s transfer remains unverified because the development reference has
no 5 MS/s positives.

The prior synthetic pilot, noise, and tone arrays at 2.5 and 5 MS/s are evaluated
only after thresholds are selected. Their results are smoke evidence and never tune
the thresholds.

Run once with:

```sh
.venv/bin/python reports/2026_09_27_ds5_cached_tracking/scout/run_scout.py
```

Timing includes receiver selection and contiguous packing plus the full native rank
call. File loading and hash verification are excluded. Server timing is not ARM
timing.
