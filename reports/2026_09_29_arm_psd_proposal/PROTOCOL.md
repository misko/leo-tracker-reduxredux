# Power-spectrum proposals for ARM GLRT

Prototype only, saved IQ, no RF or production changes. The baseline is the
sealed boundary-fallback implementation, with original individual-hit results
as the scientific reference. The question is whether a cheap raw-IQ power
spectrum can narrow the eleven coarse CFO lanes without losing useful hits.

Use DS7 for development and select a method before evaluating DS8/DS9. Inputs
are the already extracted 704 DS7 and 680 DS8/DS9 dwells. Each receiver/window
uses its own IQ only. Estimate a Welch-like averaged power spectrum with eight
2048-point Hann segments and segment mean removal. Rank the eleven original
CFO bins by similarity to frequency-shifted exact-template power spectra.
Evaluate centered log-spectrum cosine and square-root power-spectrum cosine;
no original GLRT outputs enter the estimator. Circular spectral shifting is a
sampled-signal approximation and may not model the receiver passband correctly.

First record every ranking and evaluate retention of existing candidate
proposals for top 3/5/7/9/11 lanes. This diagnostic is NOT end-to-end recovery:
rerunning candidate selection can introduce replacement candidates. Actual
recovery requires rerunning masked coarse acquisition, fine refinement and
final GLRT, then the frozen maximum-cardinality original-hit matcher (same
receiver/window, margin >=0.025, epoch <=2 samples, tracking CFO <=8 kHz).

For bounded native runs, select four evenly spaced metadata rows per rate and
edge in DS7 (32 dwells), then independently the same rule within DS8 and DS9
(32 each). Selection must not depend on spectral scores or original hits.
Include a full-eleven-lane control and zero-input/synthetic tests. If confidence
gating is evaluated, record its threshold before held-out dataset scoring.
Failure of a reduced search must not be treated as evidence that omitted lanes
contain no hits: a successful strong detection can coexist with a missed weak
one. Do not claim a no-hit fallback preserves all original hits.

The native prototype packs selected CFO lanes into four-wide SIMD groups,
preserving original per-lane arithmetic, epoch search and downstream refinement.
It consumes a per-window mask prepared from IQ-only PSD estimates. Until PSD
estimation itself is ported and timed on ARM, native timings exclude that
overhead and are only the GLRT portion of a proposed pipeline. Report losses,
new positives, fallback usage and actual work; do not infer ARM speedup from
host PSD timing or lane-count ratios.
