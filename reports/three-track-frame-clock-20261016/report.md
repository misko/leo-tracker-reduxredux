# Frame timing and carrier identity across channels

Recording: `fast8-auto-20261016-161535-99008d35-1-lower`, RX1. Times below are seconds from scan origin.

The displayed frame-phase curves do not establish that CH5 and CH8 belong to different satellites. The carrier measurements favor candidate 69522 for both, and for CH6 before and after 210 seconds. CH2 remains consistent with the same candidate under the separate cross-band calibration investigation; visual alignment of CH2 and CH6 is supporting context rather than identity proof.

## What the original figure can establish

Each channel has a separate constant phase removed using its fitted value at 185 seconds. Consequently proximity near that epoch is partly imposed by the display. CH6 starts at 195.403 seconds, so its normalization at 185 seconds extrapolates outside its observed interval. CH2 ends at 194.164 seconds: these two groups have no simultaneous measurements.

The differences in slope between CH5, CH8 and CH2 are real in the frame-phase measurements. They need not imply different spacecraft. Published Starlink measurements show that beams from one spacecraft can have different frame offsets and rates, and that frame and carrier clocks are partly independent. This is a possible explanation, not a demonstrated physical cause for this recording. See [Timing Properties of the Starlink Ku-Band Downlink, sections IV and VIII](https://arxiv.org/html/2501.05302v1).

## Carrier candidate check

The existing plotted CH5/6/8 groups were re-searched against all 1,035 regional candidates, with calibration and position frozen. Each candidate could adjust timing within ±5 seconds; no additional channel frequency offset was fitted. These groups were originally selected using model assignments to 69522, so the search is conditional evidence rather than independent satellite identification. Values are descriptive fitted carrier RMS, not held-out errors or position accuracy.

| Group | Points | Best candidate | Best RMS | Next candidate RMS |
| --- | ---: | ---: | ---: | ---: |
| CH5 | 11 | 69522 | 112 Hz | 547 Hz |
| CH8 | 18 | 69522 | 171 Hz | 670 Hz |
| CH6 before 210 s | 20 | 69522 | 103 Hz | 786 Hz |
| CH6 after 210 s | 5 | 69522 | 73 Hz | 2,015 Hz |

![Carrier residuals at fixed calibration and orbit timing](carrier_identity_checks.png)

## CH6 near 210 seconds

There are two distinct features:

- The pre-change quadratic already turns near 209.409 seconds. The subsequent downward trend alone does not require a new source.
- A frame-phase discontinuity lies between the last pre-change sample at 209.242 seconds and the first post-change sample at 211.724 seconds. A quadratic plus a step fits an 18.326-sample jump, approximately 7.33 microseconds at 2.5 MHz. Its RMS is 0.281 samples, compared with 3.311 samples for one continuous quadratic. Allowing a rate change as well gives an 18.381-sample step and 0.084-sample RMS. These are descriptive fits at the user-identified boundary, without an independently selected change-point test.

With fixed calibration and the same 69522 orbit timing, carrier RMS is 103.9 Hz before the boundary and 108.0 Hz afterwards. There is no corresponding large carrier jump in these measurements. A frame-clock adjustment, a switch between beams from the same spacecraft, or a timing-estimator change remain hypotheses. The five post-boundary observations limit confidence; a satellite switch is not established.

![CH6 smooth curvature and frame-phase step](ch6_phase_step.png)

## Consequence for modeling

Satellite identity should be shared where carrier and orbit evidence support it, while frame phase and rate may require channel- or beam-specific terms and occasional discontinuities. A frame-phase step should not automatically shift observation timestamps, introduce a carrier-frequency jump, or force a new satellite identity. The broader recovery investigation still has a failing reverse cold-start fold; this frame diagnostic does not resolve that failure.

The JSON files contain the fitted values and qualifications. The carrier search scripts retain their original deployed-package and external-corpus dependencies; they are not standalone reproduction entrypoints.
