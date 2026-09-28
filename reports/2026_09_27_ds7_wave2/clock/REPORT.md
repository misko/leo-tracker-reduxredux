# Receiver drift: actual local sensitivity screen

The first frozen single-recording baseline now has a receiver-drift Jacobian screen against its real position, recording-time and per-track-offset columns. The weighted design has rank **61/61** and scaled condition number approximately **55.35**. With both receiver drift columns present, the normalized projection remaining for receiver 0 is **0.594** and for receiver 1 **0.941**. Both exceed the previously declared 0.05 threshold.

This clears an additional local numerical prerequisite. It does **not** admit a calibrated clock variant: the calculation freezes candidate responsibilities and positive Student-t IRLS weights at the baseline prediction. It is not the full mixture likelihood information, a global search, or a nonlinear injection/recovery experiment. One track's maximum candidate responsibility is only 0.249, so identity uncertainty cannot be ignored. Independent drift bounds remain absent from the supplied evidence.

The screen explicitly checks two unit conventions. A drift in canonical measurement Hz/s differs from a physical baseband drift: exported CFO is normalized to 11.2 GHz, so the latter must be multiplied by `11.2 GHz / actual RF`. Both conventions pass this conditional screen; neither result chooses a physical model or establishes calibration. The earlier clock specification's unscaled baseband wording needs this distinction before any fit.

Synthetic +/-1 column recovery is accurate to floating-point precision, but those values are algebraic test amplitudes, not physically established drift bounds. No clock-position fit, geographic score, IQ read, cross-capture sharing, or source mutation occurred.

Evidence: [final receipt](conditional-jacobian-final.json), with input/code hashes. The initial receipt preceded a line-wrapping-only lint repair. The tool is `tools/ds7_clock_jacobian.py`; its two component tests check frequency-normalization units and receiver isolation, alongside the existing identifiability/confounding tests.
