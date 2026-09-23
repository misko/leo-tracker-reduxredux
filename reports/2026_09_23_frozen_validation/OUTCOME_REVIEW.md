# Independent outcome review

Reviewed 2026-09-23 after validation completion. This review inspected the
sealed baseline, timing, and validation result artifacts; the frozen selection
source; the selection table; accounting; and the displayed validation plot. It
did not inspect or access any final TEST artifact.

## Artifact integrity and coverage

| Artifact | Verified SHA-256 |
| --- | --- |
| `baseline/inference.json` | `61d04af0cc8d95adaec8e81ac8a0c9d8db49497b09a73b6aa7d064c7e4ade8b7` |
| `timing/inference.json` | `ca24132f58490641e7be14b2abc2a4466d458043d74693c491e957951f5ab5c3` |
| `results.json` | `ef36be4d8c739eea59c0f2a0b076ac847d4650cbee78bd4d06e124f5da1a5aff` |
| `plot.py` | `a097d5fa7f26631a8bc81cb39a9ec859548c425d5ec4fc3fd7d40bd447a76a6a` |
| `validation.png` | `3c8ad5ef62edc5de06d0db9fe5cbf5d1892ffb6d81d835cc66491f0ab4486ecd` |

The three JSON digests match their adjacent seal files. `results.json` binds
the sealed baseline and timing inference digests and the frozen evaluator and
selection source hashes. It contains exactly 112 rows: 16 per configuration
for the baseline and each of six timing configurations. All seven
configurations have complete expected group/view/prior coverage. There are no
recorded failures, nonfinite reference errors, prior escapes, visibility
failures, timing-boundary arms, or failed timing stopping rules; all seven are
therefore eligible under the frozen rule.

## Selection reproduction

Re-running `selection.select` on the sealed 112 rows reproduces the recorded
selection exactly. The selected configuration is global epoch at 0.2 s:
mean regime error 8.355389 km and worst row error 33.764833 km. Per-scan epoch
at 1 s has mean 8.358919 km, within the 0.010 km tie tolerance; the frozen
family order correctly chooses global epoch before per-scan epoch. The complete
eligible comparison is shown in `selection_table.md`.

The selection implementation follows the frozen weighting: average the two
starts within each group/view, average 6 and 16 for medium duration, weight
short/medium/long equally, then weight the two groups equally. It does not
treat the correlated starts or nested views as extra independent groups.

## Display and scientific interpretation

`validation.png` is consistent with its source: each panel is one frozen group,
lines average the two starts, bands show their range, x values are the frozen
nested scan counts, and the position panels include the 0.3 km target. It
displays all seven configurations without missing-arm gaps; this matches the
112 complete rows and all-eligible selection result.

No validation row reaches 0.3 km. The selected model's kilometre-scale mean
and 33.8 km worst row do not support a sub-300 m claim. Moreover, this is only
two grouped validation blocks with correlated nested views and starts; even a
better numerical result here would not establish broad reliability. The
protocol's final TEST remains necessary for the one frozen post-selection
evaluation, and further generalization would require new prospective cohorts.

No actionable numerical-selection defect was found. One reporting-integrity
limit remains: `plot.py` is readable and correctly consumes sealed results, but
its hash is not listed in `execution_sources.json`; the displayed plot is not a
source-bound part of the numerical seal. This does not affect the sealed rows
or selection, but a future publication should bind the plotting source and
artifact digest explicitly.
