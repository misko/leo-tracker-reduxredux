# Source-consistent track selection: coverage retained, mixed single-scan results

A deterministic source-consistent subset eliminates probe-group reuse while retaining **77.7–82.2% of training observations** in the three pilot scans. It improves reference distance on DS7 and DS8 and worsens DS9. All three selected fits remain beyond 3.8 km, so this pilot does not establish subkilometre accuracy or justify replacing the pooled baseline.

| Pilot | Tracks before → after | Training coverage retained | All-track reference distance (m) | Source-consistent distance (m) | Matched retained-track held change (nats) |
|---|---:|---:|---:|---:|---:|
| DS7 | 56 → 41 | 79.1% | 4,555.0 | 4,098.0 | +10.70 |
| DS8 | 64 → 49 | 82.2% | 9,271.8 | 8,636.4 | −2.42 |
| DS9 | 64 → 46 | 77.7% | 3,721.8 | 3,825.9 | +5.26 |

These are individual-scan fits for the first chronological scan in each existing N24 pool. They are not dataset-level performance or medians. [Full-precision results](summary.json) · [Frozen protocol](PROTOCOL.md)

## Why enforce source consistency?

The archived `_trajectory_hypothesis_tracklets` implementation explicitly constructs separate interpretations in which a probe's source group contributes at most one candidate. Its docstring says the line detector can find several paths through top-K candidates from one probe. This establishes a contract-level distinction between alternatives and coexisting observations.

The archived numerical-input `_graphs` function collects eligible track graphs across hypotheses. The baseline research export then emits these tracks together, while the geographic mixture sums their track likelihoods. The [quality sidecar audit](../2026_09_29_quality_metadata_corrected/README.md) demonstrates shared source groups in the resulting exported set. Unique track or observation IDs alone do not enforce the original one-source-per-hypothesis rule.

Source evidence is preserved in the [trajectory implementation](../2026_09_28_full_manifest_inputs/runtime-sources/leo.analysis.persistent_hop_trajectory.py) and [numerical-input preparation](../2026_09_28_full_manifest_inputs/runtime-sources/leo.operations.adaptive_tle_position_inputs.py), with pinned runtime hashes verified in the sidecar audit. This finding concerns the research export/model combination; no claim is made here about every current production path.

## Selection and comparison

Use all-point source-group identities to build track conflicts, with no reference coordinates or held signal scores. Rank tracks by training-observation count, then ID; construct greedy closures from no seed and from every track seed. Choose the closure with greatest retained training coverage, using deterministic ID ties. This is a bounded heuristic, not a proof of globally optimal coverage or correct physical association. All selected tracks are internally source-unique, and selected tracks share no source groups.

Fit all eligible tracks and the selected subset separately using six identical generic cold/grid starts and the original q=0.2 model. Thirty-four of 36 starts qualify, and every arm has a qualified selected fit. The two unqualified starts remain in the raw results; they are not replaced. Selection uses each arm's training likelihood.

The held change compares both parameter estimates on exactly the retained track set. It does not subtract likelihoods across unequal dimensions. The discarded observations still represent lost coverage and potential useful information; the table reports that loss. All-point support identities are used to enforce consistency, including held support, so this is support-aware research selection rather than blind acquisition.

## Decision and next experiment

Retain source consistency as a scientific modeling requirement worth testing, but do not promote this greedy subset as the geographic estimator from three single scans. A matched multi-scan comparison is necessary because the stronger current results come from pooling observations across time. Preserve all-track and source-consistent arms with the same scan membership and report both retained coverage and geographic error.

If subsequently averaging alternative hypotheses, do not naively combine track-set log likelihoods with different observation dimensions: omitted data need an explicit observation model. Otherwise shorter hypotheses can win merely because fewer likelihood terms were evaluated. This pilot avoids that comparison by selecting coverage first and fitting only within each fixed arm.

## Validation and artifacts

Two selector tests verify seeded alternatives, deterministic order/ties and rejection of within-track source reuse. Actual-data checks bind sidecar rows to loaded track indices and partitions, verify disjoint selected sources, and audit timing-grid replay and selected fits. Processes finished in 6–9 seconds under 120-second caps. No retries occurred.

[selection.py](selection.py), [run.py](run.py), [launch.py](launch.py), [input/code hashes](manifest.json), all alternative subsets, optimizer starts, results and receipts, and [summarize.py](summarize.py) are retained. Reference distances are evaluated after selection. Existing source conditioning, research exposure and unquantified reference uncertainty remain.

No new RF collection, public-contract mutation, production changes or remote publication occurred.
