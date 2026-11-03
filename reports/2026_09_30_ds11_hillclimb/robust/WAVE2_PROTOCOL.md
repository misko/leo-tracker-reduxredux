# Exploratory robust-likelihood Wave 2 follow-through

This is a predeclared amendment after the original eight-scan robust screen was
complete. It does not revise that screen's decision: all four original arms
failed the original requirement of at least a 10% median-error reduction.

The bounded exploratory question is whether either of the two near-screen
arms, frozen df8/scale-100 Hz or df4/scale-200 Hz, shows a small but consistent
improvement over all 32 original DS11 recordings. Both had 8/8 qualified screen
fits and 6/8 paired wins. Their screen medians improved by only 0.63% and 0.40%,
respectively, and therefore did not pass Wave 1.

Run exactly variants `df8` and `scale200` on original indices 1, 2, 3, 5, 6,
7, 9, 10, 11, 13, 14, 15, 17, 18, 19, 21, 22, 23, 25, 26, 27, 29, 30, and
31 under stage `wave2_replication`. Use the unchanged frozen robust model and
shared harness, original same-scan IID endpoint plus three generic starts,
unchanged bounds and qualification gates, a 90-second process cap, one BLAS
thread per worker, and at most two disjoint workers. Preserve every failure.

For each arm, aggregate these 24 results with that arm's eight immutable
`wave1_vectorized` screen results. A follow-through arm passes only if all 32
attempts qualify, it has at least 17 paired wins, its all-32 median error is
strictly below the matched original IID median, and its all-32 P90 is no higher
than the matched original IID P90. Report each arm independently on the fixed
32-recording denominator.

If both arms pass, select at most one: the arm with the lower all-32 median
error. Break an exact median tie by lower P90, then more paired wins; an exact
tie on all three produces no selection. Make this selection before inspecting
any additional-12 robust output. Do not run the additional-12 panel in this
step. This exposed, post-screen follow-through is exploratory and cannot erase
the original screen failure or establish independent confirmation.
