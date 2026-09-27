# DS6 receiver and channel consistency

This diagnostic completed 27 group fits (81 optimization starts) on the four
frozen development scans. It rules out a simple, consistently bad receiver or
RF channel as the sole explanation for the remaining location bias. It does not
establish sub-kilometre accuracy across DS6.

| MS/s | All-track error (km) | RX0-only error (km) | RX1-only error (km) | RX estimate separation (km) | Largest leave-channel-out shift (km) |
|---|---:|---:|---:|---:|---:|
| 2.5 | 3.779 | 4.611 | 2.389 | 4.111 | 1.620 |
| 5 | 7.292 | 8.510 | 6.560 | 2.012 | 3.636 |
| 7.5 | 0.489 | 0.398 | 0.522 | 0.259 | 0.632 |
| 10 | 6.202 | unavailable | 6.202 | unavailable | 1.486 |

The 7.5 MS/s result is supported separately by both receivers. This is useful
consistency evidence, not independent confirmation: the group fits inherit
all-track training calibration, initialization, and shortlists. The 10 MS/s
scan has no RX0 positioning tracks and remains in the experiment.

The 5 MS/s error is eastward on both receivers. Leaving channel 2 out reduces
its geographic error to 3.672 km, while leaving channel 3 out increases it to
10.753 km. Neither result justifies deleting a channel: omission decreases held
prediction on the omitted channel in both cases. The same channel omission is
not consistently helpful across scans. Of the sixteen leave-channel-out fits,
fifteen decrease held prediction on the omitted channel; the exception is the
2.5 MS/s fit without channel 1. These are diagnostics, not a channel-selection
rule. No group was promoted based on geographic error.

Protocol: all-track control, each available receiver alone, and each available
channel omitted in turn. Each fit uses the frozen training-only track scales,
whole-visit random masks, Student-t4 residual model, catalogue mixture,
continuous scan timing, local +/-12 km bounds, and three timing starts. Training
likelihood selects the winner. Included and omitted held predictions compare
against the original all-track estimate with exact propagation at each point.
The fitting script never loads the roof coordinate; `summarize.py` scores the
estimates only after all outputs are complete.

All 27 selected winners report convergence and lie inside the search bounds.
Four of 81 individual starts report abnormal termination; those statuses remain
in the outputs. The all-track controls reproduce their prior positions within
one metre. Maximum interpolated-vs-exact prediction discrepancy is 0.0202 Hz.

Two tests cover declared group membership, all input/source seals, completed
outputs, training-only selection, control reproducibility, and propagation
audits. Related objective training-isolation tests are in the preceding
track-scale experiment.

Remaining hypotheses include scan-level position/timing ambiguity and
track-specific systematic errors. A shared stationary-position fit across
scans can test whether additional sky geometry resolves the ambiguity, but
must retain scan-specific timing and random holdouts and must not replace the
full DS6 validation with success on these four development scans. No production
code or service was changed and no RF was collected.
