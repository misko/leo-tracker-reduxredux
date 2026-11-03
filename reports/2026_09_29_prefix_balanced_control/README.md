# Eight-scan selection at the same 12-scan scouting budget

Score-balanced selection does not consistently outperform a simple chronological-rank control. Spreading eight scans across the same 12-scan prefix improves reference distance on DS8 and DS9 but worsens DS7. Predictive transfer has a different ordering. Neither policy establishes reliable subkilometre accuracy.

| Dataset | Score-selected eight: reference distance (m) | Rank-spaced eight: reference distance (m) | Later-target log-score change, rank minus score (nats) | Improved targets |
|---|---:|---:|---:|---:|
| DS7 | 1,038.006 | 1,390.457 | +25.971 | 1/2 |
| DS8 | 1,231.584 | 674.808 | +8.952 | 2/3 |
| DS9 | 534.190 | 442.756 | −14.754 | 1/3 |

These are three individual set fits, not single-scan medians. Both arms use the same 12-scan availability cutoff and retain eight scans. The control selects chronological indices `[0,2,3,5,6,8,9,11]`, without examining signal outcomes. Indices are equally spread by rank; elapsed times are not necessarily equally spread. Prefixes themselves come from the existing sparse 24-scan pools.

The opposite geographic and predictive rankings on DS7 and DS9 matter: later-scan likelihood cannot be used as a demonstrated proxy for horizontal accuracy. The modest number of targets and their prior exposure preclude a general policy ranking. No policy was selected after these results.

## Additional matched comparisons

All entries below use the same target scans within a dataset. Positive values favor the new rank-spaced eight.

| Dataset | Versus first eight (nats) | Versus all prefix12 (nats) |
|---|---:|---:|
| DS7 | +214.278 | +21.950 |
| DS8 | +5.230 | +9.860 |
| DS9 | −33.722 | −17.553 |

Numerical gates passed for all 18 source starts and all eight target timing integrals. The largest quadrature discrepancy was 0.003516 nats, below the inherited 0.01 gate. Each dataset completed in 49–56 seconds under a 300-second process cap. No retries, additional RF collection or production changes were made. Source choices used training scores only. All starts, target scores, process receipts and full-precision differences are retained.

## Exposure audit: no research-blind DS7–DS9 remainder

The prior checkpoint proposed an untouched partition. Inspection of authoritative saved fits shows that none remains within these complete manifests:

| Dataset | Manifest scans | Scans in a prior complete-dataset fit | Remaining outside those fits |
|---|---:|---:|---:|
| DS7 | 88 | 88 | 0 |
| DS8 | 65 | 65 | 0 |
| DS9 | 105 | 105 | 0 |

The audit matches full input inventory IDs to prior fit-plan IDs and selected-result IDs, requires unique membership, checks parameter dimensions, and verifies qualified successful selected results and recorded execution bindings. Source hashes are in [summary.json](summary.json). Prior evidence: [DS7](../2026_09_28_ds7_full_shared/README.md), [DS8](../2026_09_29_ds8_full_shared/README.md), [DS9](../2026_09_29_ds9_full_shared/README.md).

This does not prevent useful source/target separation within these data. It does prevent calling such a partition research-blind. The current experiment is an exploratory matched control. A future blind claim needs separately reserved data and a frozen method before its outcomes are examined; this report does not authorize or initiate acquisition.

## Consequence for the subkilometre objective

Keep rank spacing as a mandatory low-cost control for future selection experiments. Retain score-balanced selection as a compression method, without claiming an accuracy advantage. The priority is now diagnosing why scans disagree and validating an abstention or uncertainty rule across separate temporal blocks, rather than optimizing selection to reproduce a potentially biased prefix fit. Any such rule needs reported coverage as well as error.

Reference distances use the existing spherical convention and operator coordinate with unquantified uncertainty. The configured center is already 809 m away. Site-conditioned candidate banks and repeated target exposure remain limitations.

## Artifacts and reproduction

- [Protocol frozen before execution](PROTOCOL.md)
- [Runner](run.py), [bounded launcher](launch.py), [input and implementation hashes](manifest.json)
- [Full results and exposure audit](summary.json), [summary builder](summarize.py)

The launcher uses exclusive output creation and intentionally refuses to overwrite a completed experiment. Re-execution requires a separate output directory. These artifacts remain local; no remote publication is claimed.
