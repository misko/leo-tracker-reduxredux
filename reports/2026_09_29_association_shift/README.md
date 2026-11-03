# Soft association response explains two displaced panel solutions

Two of the 18 panel solutions improve their training likelihood only through changing mixture probabilities relative to the pooled N24 fit. Holding the pooled probabilities fixed makes their endpoint score changes negative. The remaining 16 panels have positive fixed-probability terms, so association response is not a complete explanation for panel disagreement.

| Panel | Full training gain (nats) | Fixed pooled-probability term | Posterior response KL | Top-component changes |
|---|---:|---:|---:|---:|
| DS8 balanced-2 | +185.47 | −102.58 | +288.06 | 25/481 |
| DS9 contiguous late | +64.21 | −67.75 | +131.96 | 34/484 |

These selected panel locations previously had reference distances of 2,212 m and 3,897 m, respectively. Reference distances were not used in the decomposition. The result gives a concrete mechanism to test in these two failures: association changes can compensate for worse agreement under the pooled association probabilities.

[All 18 panels](table.md) · [Full-precision summary](summary.json) · [Protocol](PROTOCOL.md)

## What was measured

For every track, reconstruct its original q=0.2 mixture over visible retained candidates plus the unassociated linear-trend background. Compare two fixed endpoints: the N24 location with that scan's N24 timing, and the panel location with its panel timing. The exact identity is:

`panel log likelihood − pooled log likelihood = expected component change under pooled probabilities + KL(pooled probabilities || panel probabilities)`.

The KL term measures the response of soft association, including the signal/background mixture. It is not a causal fraction of error or a new optimizer's gain. Position and timing change together; this analysis does not separate their effects. Component changes denote latent mixture choices, not independently identified satellites.

All compared tracks retain identical visible candidate support between endpoints. Direct mixture sums replay the saved panel scores and independently evaluated pooled-subset scores. The decomposition therefore does not depend on dropping changed-support tracks or mismatching candidate indices.

The highlighted panels have 21 and 33 conditional-satellite MAP changes respectively. Their mean posterior total variations are 0.0574 and 0.0683, showing that a limited fraction of strongly responding tracks can matter even when most track assignments barely move. This does not prove that the changed assignments are wrong.

## Decision

Proceed to a controlled diagnostic comparing ordinary soft association with donor-frozen probabilities on the same observations. First establish whether fixing the pooled probabilities suppresses these displaced modes and whether it improves held prediction. The pooled donor already uses all 24 scans: that test would diagnose model behavior, not demonstrate an eight-scan acquisition improvement. Any useful transferable constraint would subsequently need a source-disjoint donor and explicit failure accounting.

Do not simply lock all satellite labels or eliminate soft association. Sixteen panels still prefer their own endpoint under fixed pooled probabilities; some displacement remains even without the posterior response term. Retain the pooled and per-window alternatives and avoid tuning constraints against the known reference.

## Validation and artifacts

Three synthetic tests passed: a dominant-component swap, common score offsets including extreme log scales, and 100 random identity checks. Actual-data checks cover all 18 panels and 8,656 track comparisons (the same 4,328 tracks appear once in each panel family). All per-track identities and source score replays pass the frozen tolerances. Per-dataset execution completed in about 10–11 seconds with no retries.

The [runner](study.py), [bounded launcher](launch.py), [source/code hashes](manifest.json), per-dataset raw outputs and receipts, and [summary builder](summarize.py) are retained. Exclusive output creation prevents silent replacement of results. Candidate banks remain site-conditioned; these exposed data and an unquantified reference do not establish independent accuracy. No RF collection, production changes or remote publication occurred.
