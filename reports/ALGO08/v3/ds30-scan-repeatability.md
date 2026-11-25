# Position repeatability across nearby DS30 scans

## First 53 verified recordings

The frozen time rule paired 16 distinct recordings into eight pairs. ALGO08v3 returned positions on both scans in five pairs and the candidate in six. Both builds returned both positions in the same five pairs. Across these five, median fitted separation was 0.915 km for ALGO08v3 and 1.138 km for the candidate. The candidate moved farther in three pairs. At fixed-zero calibration the corresponding medians were 0.974 and 1.333 km, with a larger candidate separation in four pairs.

The new pairs include a substantial improvement on 0262/0260, from 1.149 km to 0.186 km fitted separation, and a regression on 0430/0431, from 0.587 km to 1.138 km. The dataset observes a stationary receiver. These distances describe scatter between nearby scans. A stable offset from the surveyed position can yield a small separation. The final report applies the same frozen rule to all 204 prespecified recording pairs and discloses missing fixes before comparing separation.

The SHA-256 of the combined export for this prefix is `25162345c1acf73846a59293b1e5fd3ca446e7c6b5039be62dd09eafa3cfd293`. Pass `--limit 53` to the command below to reproduce the eight case pairs.

## First 37 verified recordings

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
