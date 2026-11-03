# Common persistence ablation

The jointly calibrated temporal model improves aggregate held score, but only
14/38 source groups improve versus temporal receiver-only. Its frozen gate
failed. Retain that failure; do not apply that model to DS11.

One distinct ablation freezes the correlation timescale to the donor-0
receiver-only estimate (7.8984961243 s) for every geometry arm. This tests geometry
at the same persistence setting, without letting the receiver-only comparator
gain a different memory timescale. Refit elevation and signed offset/slope on
donor-0 training data only, retaining priors/bounds, from previous temporal and
independent coefficients. Keep receiver-only frozen. Use the identical transfer
gate (both model controls, swap, permutation, majority of sources), derivative
checks and original donor split. This is an ablation, not a relaxation of the
failed gate and not a timescale chosen from DS11 errors. Limit the whole
calibration/validation child to 90 seconds. No DS11 fit until this gate passes.
