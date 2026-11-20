# Bounded secant fit on eight confirmation recordings

Secant published all eight confirmation positions in both calibration arms.
Each geodesic error was at most 5% higher than the error of each original v5
option.
The largest penalty versus no-repair v5 was 16.3 m. The separate six-case fresh
timing experiment measured a 1.52× median paired speedup against its reference
optimizer. [Per-recording confirmation results](per-recording.csv) · [Timing pairs](../position-fit/README.md)

The confirmation uses the exact secant solver from the six-case
timing study. It preserves the five-refresh policy, original branch proposals,
the complete archived native GLRT inputs, both calibration arms and the compact
v5 cavity decision. The first four DS26 recordings in the frozen phase-study
hash order and first four sorted DS29 recordings form this independent cohort.
[Protocol](PROTOCOL.md) · [Roster and input bindings](roster.json)

The five live numerical files matched the earlier sealed source archive
byte for byte. The replay also records the regular worker's implementation
fingerprint. The compact-projector and four original v5 position controls
use the same native observations, causal catalogue and original 25 km tile.
The archived compact-projector times come from a separate campaign.
[Source lock](source-lock.json) · [Separate fresh timing study](../position-fit/README.md)

## Position accuracy and frequency fit

The table gives median, P95 and maximum position error in kilometers on
the same four DS26 and four DS29 recordings. The full scores include the four
original v5 options and separate DS26 and DS29 distributions. [Scores](summary.json)

| Arm | Secant | Compact projector and no-repair v5 | Fixes within 1 km, all methods |
|---|---:|---:|---:|
| `c0` | 0.5774 / 0.9418 / 1.0060 | 0.5758 / 0.9426 / 1.0070 | 7/8 |
| `fitted_c` | 0.5281 / 0.9216 / 1.0101 | 0.5271 / 0.9225 / 1.0112 | 7/8 |

Seven coordinates per arm moved more than 1 m from the compact projector.
The largest movements were 20.0 m with `c0` and 18.7 m with fitted `c`. The
largest increase in geodesic error was on DS26-0301 in both arms, at 16.0 m
and 16.3 m. Median conditional RF RMS was 74.286 Hz for both methods with
`c0` and 74.244 Hz for secant versus 74.243 Hz for stock with fitted `c`.
All measured initial branch fits used five phase refreshes, and the
observation, track and branch counts matched the authenticated stock records.
[Prediction seal](prediction-lock.json) · [Original v5 role bindings](original-v5-inputs.json)

## Runtime

The new workers took 81.36–144.22 s per recording, with a 96.13 s median and
243.07 s batch elapsed time. The matching compact projector archive had a
132.96 s median on these eight recordings from an earlier campaign. The six
fresh reference/secant timing pairs matched their input, catalogue and CPU
bindings. Their per-case elapsed-time ratio ranged from 1.41× to 2.30×.
[Confirmation receipt](receipt.json) · [Fresh timing seal](../position-fit/prediction-lock.json)

## Reproduction

Each confirmation worker is pinned to one of cores 16–19 with one numerical
thread and a 480 s deadline. The replay requires the archived native files
and the pinned scientific runtime. Geographic scoring verifies the prediction
seal before loading the independent reference positions.

```sh
taskset -c 16-19 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  -m tools.pipeline_eval.qualification.secant_confirmation run
.venv/bin/python -m tools.pipeline_eval.qualification.secant_confirmation seal
.venv/bin/python -m tools.pipeline_eval.qualification.secant_confirmation score
```
