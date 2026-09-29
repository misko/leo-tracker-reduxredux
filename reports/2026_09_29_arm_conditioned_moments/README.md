# Conditioned moment screen

The approximate regular 100 Hz conditioned screen uses 32-sample blocks and
moments through order four.  At the largest 4 kHz offset and 2.5 MS/s, the
within-block phase is at most 0.156 radians and the exponential fifth-order
tail is below `8e-7` per product.  The implemented `2e-4 + 128*FLT_EPSILON`
near-maximum guard is intentionally wider than the finite random/extreme test
error; bins within twice that guard use the original FP64 direct dot product.

This is a bounded finite-input screen, not a proof of universal winner parity.
All 16 conditioned frames, frequency hypotheses, and final 16-frame GLRT stay
unchanged.  `build.py` executes host and sanitizer tests and only cross-builds
ARM artifacts.
