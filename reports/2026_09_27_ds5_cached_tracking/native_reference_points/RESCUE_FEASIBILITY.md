# Bounded same-receiver rescue: read-only feasibility

This is a post-outcome proposal derived from the frozen
`../native_candidates/results.real.json` receipt, not an executed detector or
speed measurement. It motivates a possible next implementation after the
reference-coordinate scoring diagnostic.

Keep existing native-positive receiver decisions. If any receiver is inactive,
allow at most one full Python acquisition on probe zero of one inactive receiver
per dual-RX visit. Score its retained hypotheses, then confirm the same timing
and frequency on a fresh nonoverlapping probe of that same receiver. Retain
acquired/scoring CFO separately from residual-corrected physical CFO. A proposal
from the opposite receiver is not substituted. Existing analyzer-only APIs can
process a single 20 ms, single-RX probe without IO or storage dependencies.

The application receipt contains a compatible passing probe-zero/probe-two
pair for nine of the eleven native-inactive, reference-positive receivers:
one of three at 2.5 MS/s and all eight at 5 MS/s. The two remaining 2.5 MS/s
receivers have individually positive probes but different frequency identities:

- Visit 1083 RX1: probe zero is near 444.8 kHz and probe two near 217.3 kHz;
  the probe-zero identity reappears in probe three.
- Visit 1104 RX1: probe zero is near 206.6 kHz and probe two near 434.1 kHz;
  the probe-zero identity reappears in probe four.

Thus fixed zero/two proposal coverage supports at most 76/79 reference receiver
identities if actual confirmation succeeds. Allowing later cheap confirmations
may help, but has not been evaluated. All eleven missed receivers have a native
positive on the other RX, so a one-rescue-per-visit cap does not remove their
eligibility in this development prefix. The remaining original loss is an
already-active alias mismatch and would not be repaired by inactive-only
rescue; the theoretical ceiling is 78/79 (98.73%).

The cap permits a rescue acquisition in 22 of 32 visits at 2.5 MS/s and 28 of
32 at 5 MS/s. Using the earlier application's one-receiver/probe profile means
(69.80/203.46 ms), estimated conversion and confirmation, and the current native
K1 totals gives roughly 22x/18x aggregate CPU improvement versus the complete
scanner. This deliberately mixes profile receipts and is a planning model,
not a paired measurement or a latency guarantee. The full scanner performs
22 acquisitions per visit; one extra acquisition is a much smaller budget than
rerunning all eleven probes on an inactive receiver.

Before adopting this route, measure complete call cost and all original
controls, weak/interference cases and chronological recordings. In particular,
the rescue must not reintroduce tone false positives or substitute correct
visit presence for accurate receiver timing/frequency. The choice of receiver
when both are inactive, confirmation schedule, timing transport and fallback
budget must be fixed before the next experiment's outcomes.
