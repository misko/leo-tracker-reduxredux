# How much satellite diversity could any two continuous channels retain?

On dense DS30, the survey's two channels retained the fewest original v3 assignments of any eligible pair. On the southern simulation they retained the most. Even a hindsight choice there could recover only **four of seven satellites**, using the same 450 paid stereo visits. All 16 choices per recording were counted from existing receipts. [Every channel pair and both calibration arms](measurements/survey-pairs.json)

| Input and coverage measure | Full recording | Actual choice | Range across all 16 choices |
|---|---:|---:|---:|
| DS30, stereo visits paid | 6,765 | 2,539 | 2,534–2,539 |
| DS30, originally assigned observations retained | 4,472 | 1,449 | 1,449–1,749 |
| DS30, distinct satellites | 26 | 19 | 15–23 |
| DS30, satellites seen by both antennas | 17 | 7 | 7–11 |
| DS30, satellites seen at multiple tunings | 22 | 9 | 7–13 |
| South, stereo visits paid | 1,200 | 450 | 450 |
| South, originally assigned observations retained | 266 | 152 | 76–152 |
| South, distinct satellites | 7 | 4 | 2–4 |
| South, satellites seen by both antennas | 7 | 4 | 2–4 |

The two calibration arms had identical counts on both recordings. No full-recording satellite had observations in both the first and final thirds on either recording, and each southern satellite appeared at a single tuning. The range in each row is independent of the ranges in the other rows. A channel can yield many early detections and few observations that v3 will later associate. Choosing a pair can change which satellites survive. On the southern recording all eligible pairs removed at least three satellites. A different pair's geographic error remains unmeasured. [Implementation](survey_pair_census.py) · [Actual survey fixes and timing](survey-channels.md)

## Frozen census design

Enumerate every lower/upper channel pair eligible under the frozen survey rule on DS30-0008 and the southern containing packet. Keep all early survey visits and both antennas. Use sealed full-v3 assignments only for an optimistic postfit count. For each pair count paid visits, retained stock owner rows, represented satellites, satellites observed on both antennas, satellites with any owner in both first and last thirds of the admitted timeline, and satellites appearing on two or more actual RF tunings. Count both calibration arms separately, including the values at the survey's actual choice and the full-data reference. The maxima for different metrics can occur on different pairs. Do not select a new candidate by position error, solve any extra offer, or treat retained owner counts as actual rebuilt tracks. Record every pair to make the ceiling inspectable.
