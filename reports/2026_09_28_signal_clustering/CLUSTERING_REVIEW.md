# Clustering review and alternatives

2026-09-28. This review changes the analysis and visualization, not the decoded
observations or their qualification gates. The 560/222 observation counts are
unchanged. [Open the revised comparison report](local/alternatives.html).

## Fixes and design changes

**The original figure had a row-order bug.** SciPy's left-oriented dendrogram
lists leaves from bottom to top, while `imshow` displays rows from top to bottom.
The heatmap now reverses the returned leaf order, so its rows agree with the tree.
The original numerical distances and merge structure were correct; the visual
alignment was not. All original figures and the embedded HTML have been rebuilt.
A regression test checks label order and the actual displayed matrix.

The clustering helper now rejects missing, negative, asymmetric and nonzero-self
distances; checks label/matrix dimensions and unique labels; handles fewer than
two observations without a linkage exception; and supports explicit average,
complete, single or weighted linkage. It rejects Ward at this generic distance
interface because Euclidean geometry has not been established. Ward could be
used through a separate feature interface, for example on square-root probability
vectors. See [SciPy's linkage requirements](https://docs.scipy.org/doc/scipy/reference/generated/scipy.cluster.hierarchy.linkage.html).

The **reviewed cohort contains 19 local visits with at least 10 accepted words**.
S17, with one observation, remains in the original lookup but is excluded from
this cohort. The larger, differently acquired UT reference pool is also excluded
from local-visit trees, while retained in the original comparison tables.
Ten is an exploratory eligibility threshold, not a guarantee of statistical power.

## Alternatives actually evaluated

All five methods use exactly the same 19 visits. The last column is correlation
between the tree's cophenetic distances and that method's input distances; it
measures tree representation, not satellite-identification accuracy.

| Method | Question it tests | Cophenetic correlation |
| --- | --- | ---: |
| Family JS, average linkage | Baseline frequency-profile similarity | 0.823 |
| Family JS, complete linkage | Sensitivity to using the largest between-group distance | 0.617 |
| Family Hellinger, average linkage | Alternative geometry of frequency profiles | 0.806 |
| Family Jaccard, average linkage | Shared observed vocabulary, ignoring multiplicity | 0.874 |
| Exact-word JS, average linkage | Retain rotations and polarity instead of collapsing families | 0.766 |

JS means base-2 Jensen–Shannon **distance**, the square root of divergence.
The original implementation already used distance correctly. See
[SciPy's definition](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.jensenshannon.html).
Hellinger is Euclidean distance between square-root probabilities divided by
sqrt(2). Jaccard is one minus intersection/union of observed family sets.
All three range from zero to one.

Hellinger and family JS distance rankings are almost identical (Spearman 0.997).
Jaccard is also strongly related (0.931), while retaining exact words changes
rankings more (0.801). Complete linkage uses the same pair distances as average
linkage but produces different groups. No method is selected using satellite
labels, and the highest cophenetic correlation is not evidence of the best
physical classification. Jaccard still depends on how much vocabulary a short
excerpt happens to sample, even though it ignores counts.

## Equal-count and quality sensitivity

We drew 300 random subsets **without replacement**, each containing 10 accepted
word observations from every eligible visit. Each draw recomputed JS distances
and average linkage. This provides equal observation counts and tests sensitivity
to the finite excerpts. It does not correct selection bias, temporal dependence,
unequal recording duration or receiver quality, and it deliberately discards
some information. The resulting 2.5–97.5 percentile ranges are **subset ranges,
not confidence intervals** for the transmitter population.

For sensitivity, each tree was cut into 2, 3 and 4 groups. At the illustrative
three-group cut, these pairs were assigned together at the following rates:

| Pair | Fraction of subsets assigned together |
| --- | ---: |
| S01 / S02 | 83.0% |
| S18 / S19 (likely NORAD 59199) | 78.7% |
| S13 / S15 | 59.3% |
| S22 / S23 (likely NORAD 57526) | 50.3% |
| S06 / S07 (likely NORAD 59199) | 38.0% |

These are not probabilities of shared satellite identity or branch confidence.
Group sizes and the chosen cut affect them. All pairwise results and the
two/four-group sensitivities are available in
[clustering_sensitivity_pairs.csv](local/clustering_sensitivity_pairs.csv).
The mean subsampled distance and coassignment figures summarize sensitivity;
the full-count tree remains useful alongside them.

On nine visits with at least 10 observations under **both** quality gates,
full-tier and stricter-pilot-tier distance rankings have Spearman correlation
**0.507**. Keeping the cohort fixed avoids confusing quality changes with adding
or removing visits. This moderate agreement shows that quality/acceptance choices
matter much more than switching JS to Hellinger for these data. Neither filter
is established here as ground truth.

## Recommended interpretation and next options

Use **family JS with average linkage on the eligible local cohort**, alongside
the equal-count sensitivity and exact-word comparison. Treat the tree as a way
to explore similarity, not a set of satellite classes. S01/S02 and S18/S19 recur
together more consistently than many pairs, but these results still do not
establish a satellite-specific encoding.

Two useful further experiments, not implemented in this review:

- **Bit-distance-aware distribution comparison:** transport mass between families
  using their minimum Hamming distance as cost. Current histogram methods treat
  every distinct family as equally different. This experiment would test whether
  that loses useful signal, but requires checking whether the code alphabet's
  Hamming geometry carries physical meaning.
- **Temporal comparison:** compare ordered word transitions at known frame gaps,
  with block resampling across longer excerpts or independent passes. The current
  frequency profiles discard order. Rejected frames must remain explicit gaps;
  concatenating accepted frames would invent transitions.

These address limitations in the representation and evidence, rather than
assuming a different clustering algorithm will reveal identity.

## Reproduction and validation

After generating the original saved decoding tables, run:

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_28_signal_clustering/cluster_signals.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_28_signal_clustering/clustering_review.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib --with pytest python -m pytest -q -o addopts='' reports/2026_09_28_signal_clustering reports/2026_09_28_ds7_ds8_correspondence/test_native_rates.py
```

Twenty-four focused tests pass. Tests cover invalid distances, row alignment,
metric endpoints, presence-versus-frequency differences, reproducible resampling
and full-size subset invariance, plus the existing bit and native-rate checks.
Input hashes, random seed and numerical diagnostics are in
[clustering_review.json](local/clustering_review.json). Data, generated plots and
HTML remain Git-ignored. No new RF collection or decoding was required.
