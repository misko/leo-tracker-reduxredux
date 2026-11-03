# One shared location across the three N24 source pools

Assume one stationary receiver location across DS7/DS8/DS9, as in the inherited
common-reference analyses; this is a modeling assumption, not independent site
verification. Combine exactly the 72 source scans from the three frozen N24
pools. Use unchanged q020 with one location and 72 independent timing offsets.

Two starts: configured center and arithmetic mean of the three qualified N24
east/north positions. Initialize each scan's timing at its N24 source fit.
Select the highest qualified training score only. Same optimization/gradient
gates as earlier; each start capped at 180 seconds, two concurrent workers.

Compare the selected joint position and the unoptimized equal-mean position
on the same fifteen frozen outside scans. Score under original complete-track
q020 with uniform [-5,+5] s timing integration. No target fitting or tuning.
Reuse per-dataset N24, center and N8-mixture scores as fixed controls.
Target integration retains the earlier scalar/quadrature/refinement gates.
At most three target workers, 120 seconds per target.

Report source-fit qualification and all target failures. Do not turn explored
targets into a blind holdout claim. The reference is exposed and unsurveyed,
the center already lies ~809 m away, banks are site-conditioned, and the
combined pool has a longer observation span. No RF or production edits.
