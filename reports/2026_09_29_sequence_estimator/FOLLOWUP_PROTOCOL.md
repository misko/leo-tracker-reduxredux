# Fixed-drift control, specified after the primary assay

The primary result has 29/72 pilot-only drift-boundary solutions versus 4/72
sequence solutions. This motivates a separate diagnostic: is the gain merely
repairing an underconstrained two-parameter baseline?

Replay the exact same 72 inputs, selection state and splits. Add pilot-only and
sequence-assisted frequency-only fits with drift fixed to zero. Also fit a
stronger pilot-only frequency baseline using all symbols 22–221, leaving the
same 222–301 samples untouched. Use corresponding training samples for its
static gains. Preserve primary results. No threshold or membership changes.
This is a post-primary follow-up, not an originally preregistered ablation.

After the first fixed-drift replay showed that longer pilot support dominates
the short fits, add a matched hybrid: the same long pilot support plus only
the original sequence fitting interval. Profile each carrier's gain on its
own support, weighting by its sample count. Tail gains for every long arm use
only the original FIT interval; extending the assumed tail into the header is
invalid. This corrects the initial follow-up tail-gain accounting; its held
pilot comparisons were unaffected. Retain the initial follow-up output as v1.
