# Refined random-intercept numerical failure receipt

The first refined full-six attempt terminated with exit status 1 before writing
an artifact. During the mixture arm's coarse grid at `sigma=1`, the mode solver
failed on full calibration track index 78
(`scan-fw-4c56320fb5ca6994`, track
`sha256:7ac97c51b28b26befeefdeb32c96c8845ef6b1ee4812ace5632fd942b592c1f8`),
which has 16 reception rows and zero matched outcomes.

The likelihood and experiment were not changed. The numerical cause was an
interior Newton proposal that could make insufficient bracket contraction in a
flat all-miss tail. The repaired solver accepts a Newton proposal only in the
central 80 percent of the current global monotone bracket and otherwise bisects;
if safeguarded Newton exhausts its iteration budget, it performs a guaranteed
bisection fallback and retains the strict final gradient check.

The exact failing logits are frozen in the component test and agree with an
independent SciPy integration oracle. Before retry, all 344 full-six mixture
tracks completed at every predeclared coarse-grid value
`[0, .25, .5, 1, 2, 4, 8]`. This receipt records a numerical implementation
failure only; no result artifact, model change, new bound, or geographic input
was involved.
