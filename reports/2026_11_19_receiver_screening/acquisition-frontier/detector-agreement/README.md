# Which newly detected pilots also appeared in the original detector?

The differential timing hint made 802 formerly negative receiver probes positive across two complete saved-I/Q recordings. On 247 of those probes the new winning pilot matched the original capture detector’s winner in time and frequency. Three more matched another gated original candidate. On 31 the original saw a different pilot, and on 521 the original returned no positive. A pilot’s physical origin remains unknown when the two instruments disagree. [Measured stage figure](agreement.png) · [All 27,060 joined receiver probes](probes.csv.gz)

| Result on the same physical probes | DS26-0168 | DS29-0604 |
| --- | ---: | ---: |
| Stock-negative probes made positive | 401 | 401 |
| Match the original winning pilot | 116 | 131 |
| Match another original positive candidate | 2 | 1 |
| Original reported positives at other times or frequencies | 18 | 13 |
| Original returned no positive | 265 | 256 |
| Stock wins matching the original, out of all original positives | 4,313/4,729 | 3,417/3,785 |
| Wins matching the original with the hint, same denominator | 4,437/4,729 | 3,550/3,785 |

Each row of the underlying join is one valid receiver probe. The two receivers contribute 27,060 probes over 13,530 valid visits. A pilot matches within two ADC samples modulo the frame period and 1 kHz modulo the native carrier ambiguity. Requiring agreement at the absolute carrier too gives 7,694 stock matches and 7,942 with the hint. The hint lost 38 stock positives, five of which had matched the original winner. Among the 63 switches between two positive but different time-frequency candidates, 26 switched toward the original winner and 11 switched away. [Absolute and folded counts](summary.json) · [Classification and input checks](PROTOCOL.md)

The higher aggregate agreement coincided with higher fitted position errors on both recordings. DS26 went from 0.796 to 1.722 km and DS29 from 0.734 to 0.775 km. Selecting only additional detections and refitting the original tracker gave 1.473 and 0.797 km respectively. Other measurements, track membership and which satellites constrain the fit can change together. The original detector is a retrospective comparator. [Full-I/Q position distributions](../whole-replay/README.md) · [Negative-only rescue and tracking results](../negative-rescue/README.md)

The stage plot rebuilds with `.venv/bin/python -m tools.pipeline_eval.qualification.differential_agreement_figure`. To repeat the raw comparison use `.venv/bin/python -m tools.pipeline_eval.qualification.differential_agreement --runs <whole-replay-run-directory>` with the sealed capture-era archive available. [Six input digests](result-lock.json) · [Plot and row checksums](stage-lock.json)
