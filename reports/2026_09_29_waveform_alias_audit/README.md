# Alias-convention correction for waveform trajectory tests

The cross-visit research tests omitted the visit-dependent alias unwrapping
already present in localization inputs. This changes their conclusions. The
corrected two-point test favors refinement on 13/18 tracks, while the corrected
four-point test **worsens pooled held prediction error**. Do not use the earlier
wrapped-frequency aggregates as evidence about dealiased trajectory quality.

| Test | Dataset | Cached trajectory NMSE | Refined trajectory NMSE | Improved tracks |
|---|---|---:|---:|---:|
| Two points | DS7 | 0.945485 | 0.937928 | 4/6 |
| Two points | DS8 | 1.016390 | 0.958762 | 5/6 |
| Two points | DS9 | 1.038160 | 0.885512 | 4/6 |
| Two points | All | 1.000012 | 0.927401 | 13/18 |
| Four points | DS7 | 0.953835 | 0.942730 | 5/6 |
| Four points | DS8 | 0.962896 | 0.949431 | 2/6 |
| Four points | DS9 | 0.901609 | 0.961135 | 2/6 |
| Four points | All | 0.939447 | 0.951099 | 9/18 |

Means weight each track equally. Lower held-pilot NMSE is better. The two tests
use different visits and forecast horizons, so these rows do not isolate the
effect of the number of training visits. Four-point refined weighting gives
0.951164 NMSE versus 0.951099 without weighting, still no aggregate improvement.
The local cached-held controls remain 0.904594 and 0.911522 for the two tests.

## Error and mapping

The installed public persistent-trajectory model normalizes raw CFO to 11.2 GHz
and subtracts an integer alias multiple, with native spacing
`1 / 4.4 microseconds = 227272.727... Hz`. A lane's constant alias does not change
its slope; a visit-dependent alias does. Fitting raw CFO directly can therefore
create a spurious frequency trajectory. Upconversion phase correction within
each excerpt, addressed previously, is a separate issue.

For all selected visits we verified:

```
native_dealiased = exported_measured_hz * actual_rf_hz / 11.2e9
additive_alias = (native_dealiased - raw_cached_cfo_hz) * 4.4e-6
canonical_correction = fitted_native_residual_hz * 11.2e9 / actual_rf_hz
```

The additive alias is integral within1e-8 and is the negative of the deployed
`relative_alias_index`. All lane RFs are constant. In the 106-excerpt four-point
set, 56 visits have nonzero additive aliases, and 9/18 tracks vary alias across
their selected visits. The two-point set has7/18 such tracks. Exact source,
track, visit, time, RF and content hashes are checked. No alias is re-estimated
and held observations do not change the training hypotheses.

The corrected replay fits the existing dealiased training values, adding the
same previously fitted pilot residuals where appropriate. The held dealiased
CFO defines its evaluation reference; integer symbol-period differences are
absorbed by the per-carrier gain, so this is the same underlying pilot evidence.
No new samples, selection, pilot fits, weights or thresholds were introduced.
Before correction, every saved prior per-frame NMSE was reproduced within1e-10.

## Consequence

This is an error in the new research trajectory assays, **not a demonstrated
bug in operational localization**, whose exported observations already contain
the unwrapping. Direct per-visit pilot residual fits, frame sensitivities, and
the single-excerpt training-waveform comparison are unaffected. The prior
cross-visit offset ablation is also superseded because its trajectory baseline
used wrapped values.

The mixed corrected results do not support replacing measured frequencies with
linear extrapolations. A separate [sparse geographic shadow](../2026_09_29_sparse_waveform_position/README.md)
tests the72 directly measured training corrections on their exact original
observations, preserving aliases and all held observations. It must be assessed
on its own coverage and geographic outcomes; no meter improvement follows from
the pilot prediction scores here.

## Evidence

- [PROTOCOL.md](PROTOCOL.md), [run.py](run.py): corrected replay rules and implementation.
- [results.json](results.json): complete alias audit, corrected predictions,
  per-frame errors, prior-replay discrepancies and dependency hashes.
- [authority.json](authority.json): installed module identity/hash and deployed conventions.
- `test_mapping.py`: signed alias/RF conversion and rejecting noninteger mappings;
  both tests pass.

Both replays completed within one120-second numerical cap, using existing local
IQ and one numerical thread. No RF was collected, no production files changed,
and no new geographic truth was introduced. Original reports now point to this
correction; their original numeric artifacts remain intact. Artifacts are local.
