# Time to a stable smooth-clock fix from native acquisition prefixes

The replay uses eight authentic five-minute recordings and two exact wrong-offer controls. Every checkpoint regenerates Graph from only the native detector visits whose complete sample intervals end by that cutoff. The capture-start TLE, clock authority and Graph configuration stay fixed. A separate terminal control includes the complete native recording even when its final scheduled visit extends just beyond 300 seconds. Both RF calibration arms share each original worker. [Protocol](PROTOCOL.md) · [Source lock](source-lock.json) · [Input lock](input-lock.json)

The online policy takes the second of two adjacent published fixes at most 1 km apart. It requires at least four shared fitted NORADs and new measurements on at least two of them. A pair can qualify at 180, 240 or 300 seconds. Without a qualifying earlier pair, the policy takes the ordinary 300-second decision. Shared-orbit continuity uses cumulative native observations. It measures agreement across added measurements and does not make the two fixes statistically independent.

The first preparation attempt exposed a serialization requirement in the frozen reader. Its sample-rate field needs the following native session identifier. Returning the capture-start identifier restored the standard envelope. The published lock and results cover the canonical rerun with the same samples, timing rule and source. The faulty staging attempts ended at the parser before Graph or geolocation, and scoring remained sealed.

## Decisions and geographic accuracy

The stable rule returned all eight matched offers in both arms. It stopped two cases at 180 seconds, five at 240 seconds and one at the ordinary 300-second deadline. Both omitted offers withheld at all four prefixes and the full terminal control. Their signed clearances were 22.5 km and 30.4 km outside the tile. All 50 workers completed successfully in 131.5 seconds of batch wall time. [Predictions and orbital support](raw-prefixes.jsonl.gz) · [Sealed scores](scores.json)

| Decision checkpoint | Matched publications per arm | Median published error in km, zero / fitted | Median conditional RF RMS in Hz, zero / fitted |
|---|---:|---:|---:|
| 120 s | 6/8 | 1.743 / 1.588 | 149.10 / 118.55 |
| 180 s | 8/8 | 0.756 / 0.834 | 142.56 / 91.14 |
| 240 s | 7/8 | 1.037 / 0.806 | 140.63 / 91.69 |
| 300 s | 8/8 | 0.865 / 0.888 | 158.54 / 113.89 |
| Full terminal | 8/8 | 0.865 / 0.888 | 158.52 / 113.89 |
| Stable stop | 8/8 | 0.956 / 0.710 | 140.63 / 91.71 |

The stopped P95 errors were 3.084 km and 3.077 km, compared with 1.920 km and 1.718 km at the terminal control. At DS26-0122 the qualifying fixes moved only 11 m at zero calibration and 113 m with fitted calibration. Its stopped errors were 4.088 km and 4.080 km, versus terminal errors of 1.890 km and 1.882 km. Agreement with new observations can preserve a common location bias. One fixture, DS29-0082, published at 180 seconds, withheld at 240 seconds, and published at 300 seconds. The adjacency rule correctly waited for the deadline in both arms. All eight terminal Graph digests and exact calibrated endpoints matched the already published full-native smooth-clock rows. The strict 300-second and original terminal positions differed by at most 2.2 m.

## Timing boundary

The native worker wall time measures a pinned host process reading stored detector factors, rebuilding Graph and running the original smooth-clock solver. Raw IQ detection and board timing are outside this boundary. Archived delivery brackets govern each measurement's availability. The serial overlap scenario puts that measured host work after its acquisition deadline and last delivery, delaying it if the preceding fit is unfinished. Median scenario time was 243.6 s at stable stop versus 305.9 s with a single terminal worker. The seven early stops gained 59.4–122.7 s, with a median gain of 62.3 s. The eighth waited for 300 seconds and lost 0.9 s relative to its measured terminal-only scenario. [Time-to-fix plot](time-to-fix.png)

Median repeated work through the selected stop was 9.82 s of summed worker wall time and 7.26 CPU seconds across the matched offers. A single terminal job had median wall time 5.67 s. The actual offline benchmark ran all five variants on every offer, including after hypothetical stops. Those 50 workers consumed 219.68 summed wall seconds and 163.33 CPU seconds. Their queue completed in 131.5 elapsed seconds across two pins, including staged file construction and supervision.

## Reproduce

The bundle path comes from `native_joint_trial.py`, and its source files are bound in `source-lock.json`. Select a fresh output directory for another run.

```sh
mkdir -p /tmp/online-prefix-report
.venv/bin/python -m tools.pipeline_eval.qualification.online_prefix_trial \
  --work /tmp/online-prefix-work --report /tmp/online-prefix-report --cpus 1 10
.venv/bin/python -m tools.pipeline_eval.qualification.online_prefix_trial \
  --score --work /tmp/online-prefix-work --report /tmp/online-prefix-report
.venv/bin/python -m tools.pipeline_eval.qualification.online_prefix_figures \
  --report /tmp/online-prefix-report
```
