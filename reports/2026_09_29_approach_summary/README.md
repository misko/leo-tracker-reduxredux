# DS7–DS9 localization approach comparison

Snapshot after complete DS9 and consecutive-panel evaluations. Errors are horizontal metres against
the exposed, unsurveyed operator reference. Single means the median across
independently fitted scans; set means one position fitted jointly from the
specified recordings. A dash means unmeasured, not zero. Panel sizes and
memberships differ: these rows are not all matched ablations.

| Approach / population | DS7 single median | DS7 set | DS8 single median | DS8 set | DS9 single median | DS9 set |
|---|---:|---:|---:|---:|---:|---:|
| Baseline, first eight | 2,873 | 2,541 | 3,576¹ | 1,424 | 4,778 | 1,213 |
| Baseline, complete dataset | 2,571² | 677 | — | — | — | — |
| Free frequency slope per scan, first eight | 3,001 | — | — | — | — | — |
| Two receiver-specific slopes, first eight | — | 2,302 | — | 1,551 | — | 1,750 |
| Shared track scale, first eight | — | 2,287 | — | 1,391 | — | 683 |
| Shared scale plus 10-second correlation, first eight | — | 2,955 | — | 819 | — | 1,647 |
| Baseline, eight spread across time | — | 785 | — | 2,187 | — | 1,661 |
| Shared track scale, eight spread across time | — | 527 | — | 1,896 | — | 422 |
| Shared scale plus correlation, eight spread across time | — | 359 | — | 1,904 | — | 2,109 |
| Shared track scale, union 15 | — | 497 | — | 386 | — | 319 |
| Shared scale plus correlation, union 15 | — | 996 | — | 868 | — | 1,135 |
| Shared track scale, separate additional 15 | — | 564 | — | 875 | — | 1,493 |
| Shared scale plus correlation, additional 15 | — | 1,184 | — | 187 | — | 2,588 |
| Shared track scale, combined 30 | — | 411 | — | 135 | — | 352 |
| Shared track scale, complete dataset | — | 527 (88 scans) | — | 736 (65 scans) | — | 229 (105 scans) |
| Shared track scale, median of three consecutive four-scan sets | — | 2,590 | — | 2,261 | — | 1,167 |
| Shared track scale, median of three consecutive eight-scan sets | — | 2,064 | — | 1,762 | — | 870 |

¹ DS8 single-scan median covers seven returned estimates from eight attempts;
one bank export timed out. The eight-scan joint result is from the later
completed comparison. ² DS7 full median includes all 88 returned estimates,
including one boundary-unqualified position. Qualified-only median: 2,515 m.

Sources: [baseline individual panels](../2026_09_28_ds89_baseline_panel/README.md),
[full DS7 baseline](../2026_09_27_ds7_full88/REPORT.md),
[free slope](../2026_09_28_subkm_joint_slope/README.md),
[receiver slopes](../2026_09_28_pooled_receiver_slope/README.md),
[first-eight likelihood comparison](../2026_09_28_covariance_position/README.md),
[temporal coverage](../2026_09_28_temporal_coverage_models/README.md),
[union 15](../2026_09_28_union_panels/README.md),
[additional 15](../2026_09_28_outside_union_models/README.md),
[combined 30](../2026_09_28_combined30/README.md),
[full DS7 shared scale](../2026_09_28_ds7_full_shared/README.md), and
[full DS8 shared scale](../2026_09_29_ds8_full_shared/README.md), and
[full DS9 shared scale](../2026_09_29_ds9_full_shared/README.md), and
[consecutive sets](../2026_09_29_consecutive_panels/README.md). The last two
rows are explicitly medians across three joint set errors, not individual-scan
medians. Sub-km counts for four/eight scans are DS7 0/3 and 0/3, DS8 0/3 and
0/3, DS9 1/3 and 2/3. No blanket short-window sub-km claim follows.

Cross-dataset pooling estimates one common position, not three independent
dataset positions:

| Approach | Combined recordings | Joint error (m) |
|---|---:|---:|
| Baseline, first-eight panels | 24 | 862 |
| Shared track scale, union panels | 45 | 180 |
| Shared scale plus correlation, union panels | 45 | 310 |
| Shared track scale, additional panels | 45 | 230 |
| Shared scale plus correlation, additional panels | 45 | 1,080 |
| Shared track scale plus timing refinement, additional panels | 45 | 202 |

See [baseline pooling](../2026_09_28_cross_dataset_position/README.md), union
and additional-panel reports above, and
[timing refinement](../2026_09_28_timing_recombination/README.md).

Shared track scale currently has the strongest complete-dataset joint results.
Single-scan medians for this newer model remain unmeasured. Correlation and
slope corrections have mixed geographic outcomes. Smaller geographic error
does not consistently improve held-observation prediction. These results do
not establish surveyed accuracy, calibrated confidence, or unseen-site transfer.
Receiver-specific slope corrections are not a calibrated test of antenna tilt.
This table summarizes measured localization comparisons; diagnostic-only
pilot, alias and receiver-order studies do not supply comparable error cells.
