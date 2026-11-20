# Blind regional receiver scoring

Run the scorer from the repository root after the predictions are frozen.

```bash
.venv/bin/python reports/2026_11_18_blind_regional_receiver/evaluation/score.py \
  --public PUBLIC_DIR --truth TRUTH_JSON --predictions FROZEN_JSON --output OUTPUT_DIR
```

The outputs are `summary.json` and `per_query.csv`. The manifest defines the source of query IDs and their row order. Truth and prediction IDs must each match the manifest exactly. Each CSV row includes the available decisions, published and forced coordinates, distances, offered regions that contain each estimate, and the results of both the regional and position criteria. Truth coordinates stay in the input truth file.

## Geometry and outcomes

An offered tile spans 25 km on each side. Membership uses the east and north components of the zero-altitude WGS84 surface displacement projected onto the tile center's tangent plane. Both components must be within 12.5 km, with a 1 micrometer tolerance. Restricting candidates to the side of Earth facing the tile center removes the second intersection of a projected coordinate with the ellipsoid. Longitude wraps through the ECEF transform. Each present truth point must lie in exactly its designated tile. Each missing truth point must lie outside every offered tile.

A final `fix` counts as a publication. A correct-region publication names the designated region on a present query and places the coordinate inside that tile. The geometry audit records any publication outside its claimed tile, as well as any final published region inconsistent with the available regional gate decision. Position errors are absolute great-circle distances from the output coordinates to truth, using the IUGG mean Earth radius of 6,371.0088 km. These distances include every publication carrying a coordinate, including geometry violations and wrong-region publications.

For present queries, the coverage denominator includes all attempts. The summary gives correct-region publications both over all attempts and conditional on publication. The distance-only fraction within 5 km and the fraction with both correct region and distance within 5 km also use all attempts. Errors of at least 10 km are reported conditional on publication. For missing queries, any publication is false, and explicit withholding counts as rejection. The summary reports false-publication errors and includes the supplied missing difficulty strata.

Every rate carries its count and denominator. The median and P90 use linear interpolation on ordered samples. The worst value is the maximum. A distance distribution with zero samples has null values. Withheld and missing-estimate attempts stay in the CSV and in the all-attempt denominators.

## Matched controls

| Policy | Decision and coordinate |
| --- | --- |
| `receiver` | Frozen final publication and coordinate. |
| `region_only` | Frozen regional gate before the position gate, with the accepted tile center as the coordinate. The regional gate uses the observation halves, and the exact estimate uses pooled evidence. |
| `forced_rf` | Best retained RF coordinate regardless of the receiver gates. A retained coordinate with an ambiguous region can contribute distance and false-publication risk, while correct-region credit requires a declared region. |
| `forced_region_center` | Center of the best retained RF region regardless of either gate. |
| `prior_first` | First offered center in the query's region list. |
| `prior_medoid` | Offered center with the smallest sum of great-circle distances to the other centers. Ties are resolved by the center coordinates. Coincident centers share the point estimate with an ambiguous region label. |
| `always_withhold` | No publication on any query. |

The prior controls use only offered centers. A missing forced estimate has status `no_estimate`. An absent regional gate has status `unavailable`. The same-published-region comparison uses identical present receiver publications for the exact coordinate and its declared tile center. The signed distance difference is exact error minus center error.

## Dependence and runtime

A matched pair contains one present and one missing query from the same source and site, with the same observation digest, catalog digest, and truth position. The summary shows matched, incomplete, and mismatched groups. Paired counters include the four final decision combinations. They also count correct-region publications paired with a missing rejection, with a separate count for pairs that also achieve position error within 5 km. Site summaries show each site, including sites with zero publications. Site-median distributions and query-level rates are descriptive. Multiple queries sharing a site or observation provide repeated trials of that setting.

The receiver's reported per-query wall time starts from loaded inputs and includes screening, sky and tile work, fitting, and scoring. The resource summary also includes any recorded stage times and work counts. These durations cover the in-process receiver computation. Input loading, RF acquisition, upstream feature extraction, and the scoring CLI are outside the timer. Any matched calibration replay is recorded separately. A constant RF-dependent calibration term cancels in within-track differences at a fixed RF, and frequency-fit evidence and geographic accuracy are separate measures.

Provenance lists the scorer source digest, the declared receiver engine digest, the raw truth and frozen prediction file digests, and the public manifest digest. The public scoring input digest hashes the compact, key-sorted JSON mapping of scorer-read public filenames to their raw file SHA-256 digests. Query documents commit to their observation and catalog references. The scorer reads the manifest and query documents for geometry and digests, and uses observation and catalog references to verify pair matches.
