# Full-capture 20 ms GLRT and within-window robust CFO slopes

## Question

For `cap-20260821T140820-470384cc9284`, what do we see when the previously
studied `stream-0/RX0` upper-edge path is searched over the complete 60 s
capture with independent 20 ms GLRT-64 windows at 10 ms stride? In particular,
can every window also produce a robust local estimate of CFO slope from the
actual pilot frames inside that window?

## Result at a glance

Yes. The run completed all **5,999** windows. A fresh wide acquisition was
performed in every window, and all windows contained enough complete pilot
frames for one Huber degree-one line. The GLRT exact-minus-control margin passed
the current scanner threshold of 0.025 in **2,127 windows (35.46%)**. Because
adjacent windows overlap by 10 ms, that percentage is coverage, not 2,127
statistically independent detections.

![Full-capture independent GLRT CFO and robust within-window slope](figures/2026_08_23_140820_glrt20ms/cap-20260821T140820-470384cc9284-stream-0-rx0-upper-glrt20ms.png)

*Figure 1. All six panels share the complete capture-time axis. The left column
preserves the broad all-window context. Top right separates the exact and
rolled-control scores that form the top-left margin. Middle right retains only
CFO points that pass the top-left threshold. Bottom right fixes the slope axis
to the requested +/-10 kHz/s zoom. Each slope is a separate robust straight
line through the 14--15 actual-frame CFO measurements in one window. The 75 Hz
line-RMS split is an existing local-pilot reference used only to make this
dense plot readable; it is not, by itself, a qualification verdict. Every
value, including clipped slopes, remains in the JSON and CSV.*

The main observations are:

- Activity is intermittent before about 24 s, then becomes sustained. The
  longest uninterrupted margin-pass run is **34.71--45.94 s**; it contains
  1,122 overlapping windows and reaches a margin of 0.762.
- Panel B contains two distinct descending CFO ridges over part of the active
  interval: approximately 300 to 200 kHz and 510 to 350 kHz. This means a
  single “best candidate” can represent different carrier/timing basins in
  different windows. It must not yet be treated as one phase-continuous carrier.
- Of the margin-passing windows, **1,258** also have within-window line RMS at
  or below the 75 Hz display reference. Their median robust slope is
  **-3.666 kHz/s**, with a 10th--90th percentile range of
  **-4.829 to -2.645 kHz/s**.
- The clean negative-slope band is considerably more stable after about 34 s.
  High-error slopes are concentrated where the GLRT ridge is weaker or where
  the best basin can switch. A robust fit reduces individual frame outliers; it
  cannot make a wrong carrier/basin choice correct.

## Exact method

The analysis is intentionally local and linear:

1. Read the manifest-verified CI16 recording through the read-only recording
   store. The exact manifest digest is
   `sha256:d45409ea3620eccb705eac024a4d814b5c2779f13bcee974311c9f09477adb75`.
2. Schedule complete 20 ms windows every 10 ms from 0 through 60 s. This gives
   `(60.000 - 0.020) / 0.010 + 1 = 5,999` windows.
3. In each window, independently search residual CFO from -400 to +400 kHz
   using the current Standard acquisition geometry: 80 kHz coarse spacing,
   500 Hz fine spacing, 100 Hz conditioned spacing, and ten retained basins
   separated by at least 10 kHz CFO or five epoch samples.
4. Score GLRT-64 exact and 17-symbol-rolled control pilots for all ten retained
   candidates. Select the candidate with the largest exact-minus-control
   margin. No previous or next window contributes to this choice.
5. Report that candidate's `tracking_cfo_hz` as the window's single scalar
   GLRT CFO. This is what Panel B shows.
6. Using that same window-local epoch and CFO only, estimate a separate carrier
   frequency in every complete 750 Hz Starlink frame. Each frame estimate uses
   all 300 known Qin pilot symbols and all eight edge subcarriers. There are 14
   complete frames in 5,990 windows and 15 in the remaining nine.
7. Fit `CFO(t) = intercept + slope * (t - reference)` with MAD-scaled Huber
   iteratively reweighted least squares. The Huber fit downweights large frame
   residuals without deleting them or changing membership.

There are no quadratic or cubic radio terms. No trajectory, replay result,
neighboring CFO, TLE, or Kalman state is used in this analysis.

## How to read the panels

### A: GLRT detection

The vertical value is `exact_score - control_score`. The red dashed line is the
0.025 scanner threshold. This is a candidate-only known-pilot detection
statistic, not payload decoding or satellite identification.

### B: exact and rolled-control scores

The top-right panel exposes the two score components whose difference appears
at top left. During the sustained signal, the exact Qin-pilot score separates
strongly from the symbol-rolled negative control. This makes clear that the
large margin is driven by the expected pilot, not a simultaneous rise in both
templates.

### C and D: 20 ms window CFO

This is one scalar frequency offset for one winning candidate per window. The
middle-left panel retains below-threshold points as pale context; middle right
contains only points that pass the top-left threshold. The clean descending
ridges are the signal-level result. Jumps between ridges are candidate/basin
changes; connecting those jumps into one smooth Doppler curve would be an
error.

### E and F: 20 ms line slope

This is the slope of a robust degree-one line through the window's independent
actual-frame CFO measurements. Blue circles pass the GLRT margin and have line
RMS no greater than 75 Hz. Orange crosses pass the GLRT margin but have larger
line residuals. Pale gray points are fits made below the detection margin and
should be treated as noise diagnostics. Bottom left keeps a broad robust scale;
bottom right is the fixed +/-10 kHz/s view requested for close inspection of
the negative-slope band.

The slope is very short-baseline evidence: 14--15 points across 20 ms. It is
valuable for seeing whether a local straight-line model is plausible, but it
is noisier than a 50--75 ms qualified segment. Before using it as orbital
Doppler rate, adjacent windows still need carrier/basin association, phase
support, a held-out prediction check, and receiver agreement.

## Reproduction and outputs

Run from the repository root:

```bash
.venv/bin/python tools/analyze_full_capture_glrt20ms.py
```

The script performs one bounded sequential pass over the compressed recording
and runs at most four window analyses concurrently. It does not write beneath
`/srv/bulk/leo`.

- [Window-level JSON](figures/2026_08_23_140820_glrt20ms/cap-20260821T140820-470384cc9284-stream-0-rx0-upper-glrt20ms.json)
- [Window-level CSV](figures/2026_08_23_140820_glrt20ms/cap-20260821T140820-470384cc9284-stream-0-rx0-upper-glrt20ms.csv)
- [Three-panel PNG](figures/2026_08_23_140820_glrt20ms/cap-20260821T140820-470384cc9284-stream-0-rx0-upper-glrt20ms.png)

The JSON explicitly records that searches use no neighboring state while the
overlapping windows are statistically correlated. It also records every raw
window slope and fit diagnostic even when the PNG clips extreme noise fits.
