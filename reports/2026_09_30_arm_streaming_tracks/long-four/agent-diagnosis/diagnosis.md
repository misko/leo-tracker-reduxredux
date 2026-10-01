# Why rolling recovers 19/28 long tracks versus coarse hybrid 23/28

This diagnosis is read-only with respect to the frozen implementation. The
only ablation uses a copied source tree under this directory and changes the
per-lane active-bank bound from 24 to 128. It is diagnostic, not a proposed
setting.

All four rolling losses are initial-prefix losses, not premature endings. The
best forward rolling tracks start late and then reach the maintained server
end: ref12 starts at 51.447 s (64/86 sources), ref48 at 202.737 s (43/54),
ref51 at 228.953 s (45/59), and ref52 at 236.010 s (46/68). Relative to all
CFO-consistent ARM evidence, the omitted sources are respectively the first
5, 5, 14, and 22 sources. Thus final qualification or dropping a completed
early track is not the explanation; the emitted hypotheses themselves begin
after the missing prefix.

The 128-state copied-source ablation isolates active-bank pruning for refs 48
and 51. With no other code or threshold change, ref48 becomes complete at
48/54 (88.9% coverage, 92.3% in-span purity), and ref51 becomes complete at
59/59 (100% coverage, 92.2% purity). The frozen 24-state bank retains at most
16 established hypotheses plus eight two-point births each group, ranking
established paths first by total support, span, and score. Early ref48/ref51
paths therefore existed or could be extended, but lost the bounded competition
to longer/higher-ranked alternatives; later births survived after the lane's
competition changed. The 128-state run emits 921 tracks and raises overall ARM
representation from 39 to 44, so this is evidence of pruning pressure, not an
acceptable production tradeoff by itself.

The same ablation does not recover refs 12 or 52, so their prefix loss is not
explained by the 24-state cap alone. Reversing the same frozen algorithm over
time recovers ref12 at 69/86 and ref52 at 68/68, while ref48 reaches 46/54 and
ref51 only 4/59. This establishes direction/initialization sensitivity, not a
general reverse-order fix. The forward birth logic has two relevant
constraints: a candidate receives no new birth if any established hypothesis
successfully associates it, and a birth pairs only with the immediately
preceding source group because the backward loop breaks after its first group.
Those rules can prevent an early correct initialization while allowing a later
one. This bounded audit did not isolate which rule, association choice, or fit
rejection removes the ref12/ref52 forward prefixes, so assigning a more exact
cause would exceed the evidence.

The concrete answer is therefore split: refs 48 and 51 are lost through the
frozen active-bank competition; refs 12 and 52 show forward initialization or
association sensitivity before the eventual late birth, with the precise
branch unresolved. Nothing here establishes that a linear model is inherently
incapable: order, birth suppression, immediate-predecessor seeding, branching,
deduplication, and bank pruning all differ from coarse hybrid behavior.

Artifacts:

- `cap128/arm.tsv`, `cap128/evaluation.json`, and `cap128/arm.stderr` contain
  the single-variable diagnostic ablation.
- `targets.tsv` records the four reference-aligned ARM candidate sets used to
  scope attempted instrumentation.
- Root-owned `../audit.json` and `../reverse-evaluation.json` contain the
  per-point and reverse-order evidence summarized above.
