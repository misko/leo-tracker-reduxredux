# Avoid repeating already-tested model changes

This note reviews repository evidence while the frozen DS8/DS9 baseline panel
runs. It does not change panel membership, settings or qualification.

| Direction | Existing evidence | Consequence for subsequent work |
| --- | --- | --- |
| Free shared frequency slope | [Eight paired joint fits](../2026_09_28_subkm_joint_slope/README.md): median geographic error worsened 2.873→3.001 km; zero sub-km records in either arm | Do not promote this free nuisance merely because conditional held score improved |
| Constant-frequency null | [Wave 2](../2026_09_27_ds7_wave2/RESULTS.md): fixed 1% null had mean responsibility about 1.08e-11 and essentially unchanged first-record position | This exact alternative was already tried; a time-varying contamination model would be a different hypothesis requiring its own normalization, controls and abstention behavior |
| More local starts | [Wave 2](../2026_09_27_ds7_wave2/RESULTS.md): nine-start and historical-initialization checks converged to essentially the same first-record solution | A generic extra-start sweep is not the first explanation for systematic geographic error |
| Timestamp/export defect | [First-eight metadata audit](../2026_09_27_ds7_wave3/input-audit/FIRST8-METADATA-AUDIT.md): no concrete timestamp, visit-index or bank-shape defect found | Preserve the checked path; audit any new suspected defect against evidence rather than assuming a timing correction |
| Receiver/clock calibration | [Strategy review](../2026_09_27_subkm_strategy_review/REVIEW.md) and [clock prerequisite](../2026_09_27_ds7_wave2/clock/REPORT.md): host timing brackets do not certify UTC, and independent drift bounds were absent | Do not label a fitted coefficient as calibrated hardware drift or tune a timing prior to roof-distance errors |

The next distinction to establish is **individual versus pooled transfer** on
later captures. All planned individual results must be retained before judging
the panel, and pooling must use a shared-position likelihood rather than an
unreported selection of favorable individual estimates. Subsequent model work
should address measurement quality and wrong-association/contamination controls,
with the above negative results and calibration gaps kept visible. This note
does not claim those remaining directions have been validated or fully exhausted.
