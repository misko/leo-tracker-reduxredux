# Lag-3 injected-coordinate results

The frozen proposal kernel does not reliably recover these injected pilot
coordinates. This independently reinforces its failed runtime gate; it does
not measure GLRT detection sensitivity because no GLRT decision was executed.

| Constructed population | 2.5 MS/s supported coordinate matches | 5 MS/s supported coordinate matches |
| --- | ---: | ---: |
| Single pilot, integer/fractional timing and varied CFO | 3/12 receivers | 6/12 receivers |
| Pilot plus stronger tone | 0/2 | 0/2 |
| Two pilots, match to at least one | 2/2 | 0/2 |

The two successful mixture cases match trajectory `a` only; neither recovers
both injected trajectories. All eight noise/tone receiver cases produce zero
supported proposals. That small proposal-support count is not a detector
false-alarm estimate or a calibrated decision threshold.

The single-pilot construction has mean injected pilot power approximately
10–15 dB above generated noise, flat channels and no unknown QAM/data. Several
failures select timing hundreds of microseconds away from the injected pilot,
then reject their low-support phase estimates. For example, the closest
returned timing for the 2.5 MS/s zero-CFO RX0 case is 638.5 microseconds away;
the 5 MS/s integer +399-kHz RX0 case is 552.3 microseconds away. Thus removing
the lag-4 frequency alias is insufficient: this prototype also fails to
propose the correct timing on straightforward constructed inputs. A possible
cause is the 512-point projected ranking statistic's timing ambiguity, but
that explanation has not been isolated experimentally.

The comparison uses the original 2-microsecond physical-frame timing and
8-kHz CFO tolerances. `results.json` retains every proposal, support flag,
per-truth error and source/binary/dataset hash. No cases were selected after
outcomes, and neither data nor kernel was tuned following this diagnostic.
Unsupported phase fields can be zero placeholders; they are not measured CFO.

Template provenance uses the construction helper's canonical complex64 hash;
the receipt also stores the kernel's complex128-template hash. Both refer to
the same template values with explicitly different serialization precision.
Input bytes and protected sources were checked before and after the audit.

The separate real-data primitive benchmark is in `../lag3_proposal/`: caller
CPU medians are 0.461 ms at 2.5 MS/s and 0.994 ms at 5 MS/s, exceeding the
0.080-ms proposal budget at both rates. No GLRT integration, full-detector
speed claim, holdout replay, RF collection or ARM execution follows.
