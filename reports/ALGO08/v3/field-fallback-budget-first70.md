# First 70 DS30 field pairs and the fallback budget

The measured successor took **4,190.998 s** against **6,990.306 s** installed. Making every recorded failed lean proposal and subsequent ordinary fallback free would save **204.351 s**, raising aggregate wall speedup from **1.668× to 1.753×** and leaving **491.494 s** above the half-time target. The four fallbacks account for 29.4% of the measured gap to half-time.

The population is the first 70 verified original pairs in the frozen order, through DS30-0003. It includes the sealed DS30-0452 relocation and the verified installed solver failure with its recorded launch-to-exit clock. DS30-0036 is outside the population. The calculation reuses the earlier reducer's disjoint failed-proposal and ordinary-fallback clocks. Each counterfactual subtracts only its specified recorded scope from the same paid through-exit time and keeps every observed outcome. [Original reducer](field_fallback_budget.py) · [First-70 reducer](field_fallback_first70.py) · [Sealed result](measurements/field-fallback-budget-first70.json.gz)

| Scenario | Wall removed (s) | Total wall (s) | Median wall (s) | Aggregate speedup | Median paired speedup | At half time |
|---|---:|---:|---:|---:|---:|---:|
| Installed measured | — | 6,990.306 | 107.928 | — | — | — |
| Successor measured | 0 | 4,190.998 | 62.875 | 1.668× | 1.727× | 10/70 |
| Free failed lean proposal | 44.959 | 4,146.039 | 62.875 | 1.686× | 1.727× | 10/70 |
| Free ordinary fallback | 159.392 | 4,031.605 | 62.577 | 1.734× | 1.741× | 11/70 |
| Both free | 204.351 | 3,986.647 | 61.978 | 1.753× | 1.743× | 14/70 |

The prospective speedups are numerical ceilings from those scopes. Aggregate CPU speedups in the same order for the successor rows were 1.583×, 1.601×, 1.651× and 1.671×. The four disjoint scopes totaled 44.467 CPU s of rejected lean work and 158.783 CPU s of ordinary fallback. Of the 70 original routes, 62 finished lean and four withheld before the solver. DS30-0147 had the only measured successor slowdown, 121.950 s installed and 127.697 s successor. The verified DS30-0312 pair took 104.569 s installed and 89.770 s successor. [First-64 verified timing rows](measurements/ds30-routing-first64.json.gz)

| Fallback | Rejected lean (wall s) | Ordinary fallback (wall s) | Whole solve (wall s) | Recorded reason |
|---|---:|---:|---:|---|
| DS30-0147 | 16.472 | 59.334 | 79.192 | `repair_original_joint_pair_gate` |
| DS30-0073 | 9.875 | 37.911 | 50.351 | `repair_original_joint_pair_gate` |
| DS30-0312 | 9.737 | 27.781 | 40.154 | `repair_rejection_cap` |
| DS30-0003 | 8.874 | 34.367 | 46.655 | `repair_original_joint_pair_gate` |

### Measured accuracy

The successor published two more fixes in each calibration arm and had six fewer results within 2 km in each arm. Paired changes use the 64 shared scored fixes. The timing ceilings keep these measured results fixed. [Sealed result](measurements/field-fallback-budget-first70.json.gz)

| Calibration | Fixes installed → successor | Within 1 km | Within 2 km | Median horizontal error (km) | Median paired error change | Median RF RMS (Hz) |
|---|---:|---:|---:|---:|---:|---:|
| `c=0` | 64 → 66 | 37 → 29 | 63 → 57 | 0.863 → 1.070 | +223.0 m | 114.15 → 145.70 |
| Fitted `c` | 64 → 66 | 41 → 30 | 63 → 57 | 0.911 → 1.065 | +186.6 m | 114.16 → 145.86 |

### Evidence and read scope

The reducer checks the original attempt identities against the paired export, SHA-256 `d1581f38c524439e1e64215ed98e8fc6b36b054e2994c7a0fd1840a26d84334a`, and its seal, SHA-256 `b462fcfb8eb0a274abc2df0214ec08d99be3b77d1cf8ca412e3b3774a8b3ccdc`. It reuses exact first-30 route clocks and first-64 accuracy and charged timing. The original scorer evaluates only the final six authorized reference objects. [First-30 stages](measurements/first30-after-intake.json.gz) · [First-64 routing](measurements/ds30-routing-first64.json.gz)

For the final 40 pairs, compact original results, release markers and bootstrap receipts provide the route split. A completed lean entry that executed the pinned ordinary screened solver must have recorded its screened nomination. The two completed lean entries with this marker were DS30-0312 and DS30-0003. DS30-0003's exact scopes came from `reports/ALGO08/v3/measurements/ds30-0003-witness-attribution.json` at `fbec50dd6d6eb730395b70bced666d28cc7cb36f`, which pins both selected result files. DS30-0312 needed its detailed witness for exact clocks. Its recorded native digest and terminal match the original candidate, and the witness bytes match the previously sealed producer receipt. [Screened branch handoff](nomination_handoff.py) · [DS30-0312 case evidence](field-fallback-0312.md) · [First-64 producer evidence](measurements/first64-producer-transfer.json.gz)

The successful extraction read **4,592,662 logical bytes**. That includes 1,573,718 bytes of frozen plan and export, 443,590 bytes of prior studies and reference, and 2,575,354 bytes of original NVMe outputs. The latter comprised 271,567 bytes of attempt results, 85,857 bytes of release markers, 1,025,875 bytes of bootstrap metadata, and a single **1,192,055-byte** DS30-0312 witness under the **1,250,000-byte** cap set before opening it. Preliminary checks read compact metadata and made a dry reducer pass before the witness. Across the work there was one full witness read. No DS30-0003 or DS30-0036 witness was opened. No waveform, orbit catalogue, backing storage, fit, or benchmark was used. [Per-source byte counts and original witness bindings](measurements/field-fallback-budget-first70.json.gz)
