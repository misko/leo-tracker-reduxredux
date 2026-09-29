# Prepared CI16 coarse input experiment

This separate exact-output experiment extends Wave5 combined ingestion to
prepare `float_samples` and the double energy prefix during the same CI16
traversal that writes raw FP64 samples.  The preparation uses the original
operation order and fixed `32768.0` scale.  `coarse_fp32` consumes prepared
state only when its saved count matches, then clears it.  The unchanged public
complex entry resets prepared state and performs its original preprocessing.
Every invalid CI16 call also clears the state before returning.

The owned host and sanitizer unit verifies raw FP64 workspace bits, FP32 sample
bits, double prefix bits, sparse boundary regions, partial tails, stride two
and four, extrema, overflow rejection, and invalid-state reset.  Host704
reproduces all 86,439 combined candidate objects with zero changed candidates
or windows.  An ARM artifact is cross-built for reproducibility but was not
executed or timed; this experiment remains separate from the final candidate.
