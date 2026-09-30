# Phase-distribution trees cannot locate message fields

Two remaining saved hierarchies summarize regional phase distributions, rather
than ordered symbols or message bits. A direct audit of an existing recording
confirms that rearranging **99.972%** of its complex sample positions within
the four regions leaves its histogram features **exactly unchanged**. These
features cannot recover the discarded carrier/symbol ordering.

## What these trees contain

The DS7–DS9 all-recovered tree contains 11,870 tracks; 11,132 have insufficient
pilot qualification and 738 are qualified. The qualified-only tree contains
those 738 tracks. Pilot carrier bins are excluded, but known T-code is not
subtracted. Four physical-symbol regions (2–7, 8–33, 34–129 and 130–301) each
contribute equally to a 16-bin phase histogram. Square-root probabilities give
Hellinger features, and the trees use average linkage.

Within each region, the histogram pools frames, symbols and available data
carriers. Tracks at different rates have different available-carrier support.
This can be useful for waveform or recovery-quality characterization, but
histogram similarity is not bit-by-bit message agreement.

## Actual-data information-loss check

The deterministic example is the highest-pilot qualified track,
**DS9-F100-T0054**. The script verifies its source artifact SHA256, selects the
original evaluation frames, removes the original pilot bins, and reproduces
its saved histogram. It then independently permutes all complex samples within
each region. Despite changing almost every coordinate assignment, the maximum
histogram difference is zero. No new acquisition or fitted alignment is used.

This proves that these features alone cannot distinguish the original ordered
sequence from many rearrangements with different candidate field contents.
It does not prove the original recording lacks message fields, nor exclude a
distribution-level association with identity if independent evidence supports it.

## Cluster composition and quality

At the saved four-group cut:

| Hierarchy | Group sizes | Dominant group's fraction |
|---|---|---:|
| All recovered | 2, 57, 11,810, 1 | 99.49% |
| Qualified only | 2, 1, 3, 732 | 99.19% |

These are highly uneven partitions, not four well-supported peer classes.
The script also records the 2- and 8-group cuts, quality composition and median
pilot scores for every group, without selecting a preferred cut afterward.

A phase-axis concentration score—the magnitude of the second angular moment,
averaged over the four histograms—has descriptive Spearman correlation **.640**
with held pilot coherence in the full set and **.387** in the qualified set.
This shows that the feature family carries recovery-quality information. It
does not establish that quality explains every dendrogram branch. No population
p-value is assigned because tracks and sessions are dependent.

## Firmware implications

The software prefix fields and their bit positions cannot be mapped directly
onto these histogram axes or branch labels. The freshly traced role settings,
20-entry threshold mask and 60-entry threshold mask provide no missing
coordinate ordering. Interpreting a four-group cut as a two-bit firmware field
would therefore require additional ordered-symbol evidence.

Ranked interpretations are phase distribution/acquisition quality, known
waveform mixture, then an unproven distribution-level identity association.
The existing held-frame and revisit tests address identity more directly than
these whole-region histograms. No new unconstrained identity scan is warranted
by this audit.

## Reproduction

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_firmware_cluster_reaudit/phase_histogram_audit.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with matplotlib python reports/2026_09_29_firmware_cluster_reaudit/association_ledger.py
```

Ignored `local/phase-histogram-audit.json` records all cut compositions, source
hashes and the actual-data permutation result. The ledger now has 326 entries.
All 18 research-component tests pass. This completes the focused review of
these two trees, not the full investigation or exhaustive association inventory.
