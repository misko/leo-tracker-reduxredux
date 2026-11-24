# Position repeatability across nearby DS30 scans

Only two pairs of nearby scans among the first 37 recordings have positions from both builds on both scans. The candidate's fitted position moved farther between scans in both pairs. The larger difference was on DS30-0183 and DS30-0185, recorded 50.5 minutes apart. ALGO08v3 moved 0.915 km between its two fixes and the candidate moved 1.529 km.

| Scans | Start times apart | ALGO08v3 separation, fitted | Candidate separation, fitted |
|---|---:|---:|---:|
| 0086 and 0087 | 25.3 min | 1.509 km | 1.591 km |
| 0107 and 0105 | 36.5 min | Missing a fix | Missing a fix |
| 0183 and 0185 | 50.5 min | 0.915 km | 1.529 km |

With calibration fixed at zero, the candidate also moved farther on both scored pairs. Median separation at fixed zero was 1.203 km for ALGO08v3 and 1.649 km for the candidate. With fitted calibration the medians were 1.212 and 1.560 km. These short runs give two examples of variation in the estimated position of a stationary receiver. Two scored pairs are insufficient to establish how often this happens. Absolute localization accuracy is scored separately against the survey. [Case-level results](measurements/ds30-repeatability-first37.json)

## How recordings are paired

The rule was committed before calculating these separations. In the fixed benchmark enrollment order, match a newly enrolled recording with the nearest unpaired earlier enrollee by capture start time, provided their separation is at most one hour. Both recordings must be physically distinct and have the same eligible survey reference. This rule uses survey identity to restrict the evaluation to a stationary site. Neither solver sees the neighboring fix. Future enrollment cannot remove a previous match. [Pairing and scoring code](ds30_repeatability.py)

The signed manifest yields three eligible pairs at 30 recordings, the same three at 37, 30 at 100, and 204 at 455. Those are counts of matched inputs. Each build's paired fix count and the common scored denominator depend on what it actually returns. The original 455 recording identities are distinct. This comparison measures movement on repeat observations of one roof. No position adjustment or reference-site prior was applied.

The following command uses the verified combined export and its adjacent seal. Omitting the limit scores the latest verified prefix. It reads the saved predictions and enrollment metadata.

```sh
python -m reports.ALGO08.v3.ds30_repeatability "$campaign_root/rows-with-relocations.jsonl" --limit 37
```
