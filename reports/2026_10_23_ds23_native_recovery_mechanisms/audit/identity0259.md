# DS23-0259 archived native identity evidence

This is a read-only inventory of the frozen persistent-five-second discovery, not a new identity fit. The JSON contains complete archived probability vectors, candidate mappings, times and observation IDs.

| NORAD | Path suffix | RX/CH | Points | Interval (s) | c0 / fitted-c log odds against largest archived alternative |
|---|---:|---|---:|---|---|
| 65340 | 001 | 1/1 | 11 | 131.43–161.67 | 59.11 / 59.63 |
| 65340 | 002 | 1/2 | 25 | 145.27–171.88 | 125.11 / 125.62 |
| 65340 | 005 | 1/4 | 8 | 129.44–141.17 | 42.96 / 42.34 |
| 67618 | 006 | 1/4 | 23 | 143.51–173.94 | 120.07 / 120.29 |
| 65340 | 007 | 2/1 | 10 | 187.53–204.01 | 55.05 / 54.97 |

All five passed and were selected. Their archived winning probabilities round to 1.0 in both arms. The largest remaining archived probability is clutter in each case. Most alternative-family probabilities are numerical zero, so the archive does not retain usable finite score differences against every alternative. Log odds in this table are computed from the saved probabilities; they are conditional selection evidence, not independent confirmation of the physical identity.

The search compares only 13 currently active curved families: 57635, 58678, 58686, 58846, 58937, 61627, 62739, 62754, 63847, 63857, 65340, 67618 and 68289. It does not test the full causal catalogue or unknown emitters. Consequently strong conditional probability cannot resolve a wrong label outside that set versus a discrepancy in geometry, RF calibration or physical modeling.

Frozen source evidence: `ds23_graph_seeded_path_recovery.py:28–30` defines active families from retained curved rows; `:49–57` constructs predictions for those families. `probe_ds23_graph_seeded_paths.py:74–85` performs conditional identity checks and selection. `ds23_temporal_predictive_recovery.py:111–131` compares candidate-family Gaussian predictions with uniform clutter. Paths on RX2 exist for 65340 later in the recording, but this alone is not simultaneous cross-receiver confirmation of the earlier paths.

Supporting curved observations at each interval are now recorded in `identity0259.json`, including retained observation IDs and exact times. The inventory intersects physical track observations with the saved ordinary-parent curved gate IDs; unused points from those same physical tracks are excluded. All mapped gates are compatible and every retained ID maps to its physical track.

| Path suffix | Same-family curved support within interval | Other curved families in interval |
|---|---|---|
| 001 | RX2/CH2: 1 retained point | 58846, 62754, 63857 |
| 002 | RX2/CH2: 10 retained points | 62754, 63857, 67618 |
| 005 | None | 58846, 63857 |
| 006 | RX1/CH4: 6 retained points | 62754, 63857, 65340 |
| 007 | RX2/CH2: 13 retained points | 58937, 67618 |

Thus 65340 paths 001 and 002 have simultaneous cross-receiver curved support under the parent assignment. The short path 005 has none; path 007's support is on its own receiver. For 67618 path 006, the parent same-family points are on the same receiver and channel. These observations already condition the discovery calibration and assigned identities, so they are not independent identity confirmation. Other-family rows describe calibration context rather than direct support for the proposed label.
