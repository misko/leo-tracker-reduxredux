# DS26 residual inventory after published ALGO03 v2

All 159 DS26 fast-scan slots in the sealed full-evaluation candidate inventory were accounted for. The 148 completed v2 terminals supply a published association decision. Every one of their 19,374 graph tracks was examined, retaining 5,451 tracks with at least one residual original GLRT observation: 4,995 wholly unassociated tracks and 456 partially associated tracks. Seventy-eight retained tracks have one point and zero duration.

The completed scans contain 650,404 original GLRT observations: 461,708 published associated IDs and 188,696 residual IDs. Of the residual IDs, 113,195 lie in the existing graph and 75,501 lie outside it. The latter are counted explicitly but cannot be ranked as graph tracks without a separate track search.

Support is the selected arm's exact `selected.arms[arm].associated_ids`. For `ALGO02_fallback` terminals, support is the baseline selected arm's published `gates.tracks` and `linear_gates` observation IDs. Published point memberships were verified identical between `c0` and `fitted_c` in all 148 cases. We do not subtract extra associations recovered by a numerical replay: 6,409 replay-owned but unpublished IDs remain residual. This distinction matters because the earlier recovery inventories themselves used replay memberships and omitted tracks wholly owned in that replay.

## Longest first-to-last residual spans

| Rank | Case | Track index / RX / CH | Residual points | Start–end (s) | Span (s) | Largest gap (s) | Longest run with gaps ≤5 s (s) |
|---:|---|---|---:|---|---:|---:|---:|
| 1 | DS26-0265 | 70 / 1 / 4 | 120 | 211.045–299.306 | 88.261 | 2.129 | 88.261 |
| 2 | DS26-0223 | 22 / 1 / 2 | 80 | 73.451–159.642 | 86.190 | 9.933 | 60.301 |
| 3 | DS26-0050 | 1 / 1 / 1 | 77 | 37.580–121.968 | 84.388 | 9.224 | 46.450 |
| 4 | DS26-0251 | 88 / 1 / 7 | 67 | 132.508–216.515 | 84.006 | 6.377 | 46.076 |
| 5 | DS26-0094 | 86 / 1 / 6 | 46 | 172.475–252.947 | 80.472 | 9.928 | 22.692 |
| 6 | DS26-0092 | 108 / 1 / 6 | 102 | 126.401–206.489 | 80.088 | 3.192 | — |
| 7 | DS26-0004 | 105 / 1 / 6 | 61 | 206.140–285.881 | 79.741 | 6.027 | — |
| 8 | DS26-0064 | 107 / 1 / 6 | 44 | 157.340–236.756 | 79.416 | 5.675 | — |
| 9 | DS26-0120 | 107 / 1 / 8 | 90 | 135.699–213.689 | 77.990 | 6.027 | — |
| 10 | DS26-0010 | 17 / 1 / 2 | 91 | 101.787–179.423 | 77.636 | 6.380 | — |

All ten are wholly unassociated. The existing graph quality label is `insufficient_support` for fifth-ranked DS26-0094 and `structure_flagged` for sixth-ranked DS26-0092; the other eight are `no_structure_detected`. These labels, graph polynomial RMS, and exact point IDs are retained in the machine-readable rows. A graph polynomial is not a satellite orbit and its RMS does not establish identity.

The requested ranking uses first-to-last remaining-point duration. It does not imply continuous evidence between points. No residual track has duplicate timestamps; observation IDs were checked unique both within each source observation list and within each graph track. The inventory also supplies longest sample-run spans for adjacency gaps ≤2, ≤5, and ≤10 seconds. These thresholds are explicit descriptive summaries, not detector gates or a claim of continuous RF capture.

## Eleven slots without a completed published v2 decision

Ten failed or unqualified baseline scans retain 1,225 raw graph tracks and 41,806 GLRT observations. They are inspected separately because there is no completed v2 association set to subtract. Their largest raw graph spans are:

| Case | Raw graph tracks | GLRT points | Longest raw graph span (s) |
|---|---:|---:|---:|
| DS26-0132 | 133 | 4,446 | 68.035 |
| DS26-0156 | 130 | 4,880 | 75.482 |
| DS26-0160 | 121 | 4,187 | 64.499 |
| DS26-0181 | 108 | 3,851 | 73.732 |
| DS26-0191 | 144 | 4,375 | 74.769 |
| DS26-0199 | 104 | 3,844 | 77.641 |
| DS26-0273 | 156 | 5,099 | 76.224 |
| DS26-0281 | 120 | 4,083 | 69.103 |
| DS26-0285 | 108 | 3,795 | 74.055 |
| DS26-0289 | 101 | 3,246 | 72.654 |

Even treating every retained failed-scan graph point as unassociated, none can displace the completed-scan top five: their maximum raw span is 77.641 s, below the fifth-place cutoff of 80.472 s. DS26-0172 has no existing public GLRT input and no retained graph. There can be no claim about unrecorded or unavailable evidence for that slot.

## Artifacts and reproduction

- `inventory.json.gz`: exhaustive residual graph rows, per-scan accounting, failure coverage, and SHA-256 provenance for 761 source files (compressed for publication).
- `residual_tracks.csv`: all 5,451 residual tracks ranked by decreasing duration, then point count.
- `top10.json` and `top10.csv`: exact IDs, indices, keys, interval, gaps, RX/CH/RF, and inventory/descriptor/terminal/graph paths for immediate investigation.
- `per_scan.csv`: all 148 completed-scan accounting rows.
- `unavailable.json`: all 11 unavailable candidate slots, failure reasons, and raw graph summaries.
- `unavailable_raw_graph_ranking.json` and `.csv`: separate ranking of all 1,225 failed-scan raw graph tracks.
- `reproduce/inventory_ds26.py` and `reproduce/test_inventory_ds26.py`: standalone standard-library implementation and four definition tests.

Run from the `reproduce` directory on the host containing the recorded corpus paths:

```bash
python3 -m unittest test_inventory_ds26.py
python3 inventory_ds26.py
```

The script verifies each completed terminal against the sealed candidate inventory hash, records source hashes, checks point-array lengths and stable track identities, and confirms the two published calibration arms have identical memberships. It reads sealed local artifacts only: no numerical inference replay, GPS, satellite catalogue, new collection, or production mutation. This inventory ranks duration; satellite explanations and recovery decisions belong to the separate investigations.
