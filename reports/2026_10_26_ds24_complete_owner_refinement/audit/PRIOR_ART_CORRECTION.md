# Correction: continuous GLRT64 refinement is established prior work

The preceding DS24 review missed the directly relevant August 23 implementation.
The [existing report](https://github.com/misko/leo-tracker-reduxredux/blob/6c21d627fbb08e4c561eafe5a5c3606369e0f4e1/reports/2026_08_23_470384_continuous_glrt.md)
and [source](https://github.com/misko/leo-tracker-reduxredux/blob/6c21d627fbb08e4c561eafe5a5c3606369e0f4e1/tools/report_470384_continuous_glrt_refinement.py)
already preserve the 20 ms GLRT64 likelihood, symbols 2–65, 512-bin initial
search, fixed acquired CFO and frame epoch, frame-wise coherent power and
normalization. They continuously refine both exact and control peaks using
analytic derivatives with safeguarded Newton and golden-section fallback.
This is closer prior art than the earlier full-frame estimator references.

The August code uses a local interval of one bin width on either side of the
discrete maximum; the present implementation confines the optimum to its
original half-bin cell. That implementation detail does not make continuous
GLRT64 refinement a new scientific method. The earlier report already evaluated
788 associated windows, reporting a median absolute correction of 77.2 Hz and
median exact-score gain of 0.153%. Its separate 300-symbol even/odd prediction
checks a longer pilot and must not be attributed solely to sub-bin refinement.

The current contribution is a deployment-specific transfer: exact historical
DS24 detector replay, complete preselected accepted-owner coverage, native-ID
and alias-preserving replacement, and matched nonlinear position propagation
in both c arms. The synthetic controls establish behavior under their declared
sampled waveform; recorded score increases establish optimization of the
existing objective. Neither alone establishes physical CFO truth or better
localization. The current matched position experiment addresses the latter.

This correction changes attribution and interpretation, not the frozen
measurement or position protocols. Previous sealed studies and their original
publication commits remain immutable; the current report should link here.
