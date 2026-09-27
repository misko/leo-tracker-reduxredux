# Independent design review

The bounded rescue is scientifically testable as written. The revised design
closes the main ambiguity in the feasibility note: Python acquisition supplies
only a causal proposal, while unchanged native guided scoring must accept both
probe zero and the fresh, nonoverlapping probe two. The resulting pair therefore
has one native contract rather than silently mixing a Python first member with a
native second member. This also explicitly exercises the qualified guarded API
at the visit-1104 probe-zero rounding edge that the earlier unguarded API
rejected.

The timing transport must be implemented in relative integer coordinates. For
a Python integer epoch `e0` at probe start `p0`, the phase supplied at probe
start `pq` is

```text
local_q = (((e0 + p0 - pq) * 750) mod sample_rate_hz) / 750
```

Probe zero to probe two happens to preserve the same local phase because 20 ms
is exactly 15 frames at 750 Hz. This coincidence must not become a general
`local_q = e0` rule: probe three is displaced by 22.5 frames and needs a
half-period phase shift. Absolute source counters remain integer, with any
fraction stored separately.

For each proposed candidate, the implementation should explicitly check both
native observations against the transported Python hypothesis, as well as
against each other:

- same configured receiver and exact probe-zero/probe-two geometry;
- status zero, valid bounds and support, at least two support frames,
  fractional completion, and margin at least 0.025 for each native member;
- circular native timing error from the corresponding transported seed within
  2 microseconds for each member, followed by the same mutual phase gate;
- returned physical CFO within 8 kHz of the probe-zero Python physical CFO for
  each member, and within 8 kHz between native members; and
- acquired/scoring CFO preserved separately from residual-corrected physical
  CFO, with no wrapping or clamping at an API boundary.

The native timing and physical CFO are conditioned on the supplied proposal.
Guided scoring is fresh-sample evidence, but it is not an independent timing or
frequency acquisition. In particular, expected physical CFO participates in
native alias and innovation handling. Reports should describe the second point
as causal conditioned confirmation rather than an independent refit.

The design now fixes RX0-first inactive-receiver choice, original candidate
order, probe two, ten candidates, and stop at the first passing pair. The call
budget should be interpreted as at most ten native probe-zero point calls plus
ten native probe-two calls; candidates rejected at probe zero need no probe-two
call. Timing must include Python conversion/acquisition/scoring, every native
point attempt, controller assembly, and failure paths. Tests should assert this
short-circuit count and deterministic tie behavior.

## Interference safeguards

Neither `conditioned_glrt64_score` nor native guided scoring performs the blind
path's nuisance-tone conditioning. Existing cache challenges tested guided
points seeded by an earlier real pilot. They do not cover the new failure mode
where a tone drives Python acquisition and supplies its own epoch and CFO.

The predeclared mirrored-negative audit materially improves this coverage. Its
metadata selection is exactly the 12 independent legacy controls with required
inactive policy, false `expected_active`, and two constructed-negative/no-pilot
receiver truths: six per rate, comprising six noise and six tone parents. Run
each parent in original and RX-swapped orientation with fresh state and fixed
RX0 rescue selection. Swap receiver truth provenance with the IQ, assign the
derived `::rxswap-v1` identity, and record both the parent NPY hash and the
derived CI16 payload or newly materialized NPY hash. A derived case must never
carry the parent's raw hash. These are 12 paired orientation tests and 24
executions, not 24 independent negative realizations.

If the primary native method unexpectedly activates on a negative, record that
false positive and mark rescue policy-ineligible. A forced-rescue diagnostic
would need separate preregistration; it cannot replace the policy result.

## Remaining limits

The existing negative controls cover white noise, tones and multitones at both
rates, but not a broad tone frequency/phase/amplitude distribution, pulsed
interference, or pilot-like cyclostationary interference. Existing two-pilot
and pilot-plus-tone controls will usually be native-active and therefore do not
exercise the rescue branch. Passing this development set does not establish a
rare false-alarm rate or multisignal rescue safety.

The fixed probe-zero/probe-two opportunity count of 9/11 missed inactive
receivers is only a development ceiling. It does not show that Python proposals
survive both native point gates. Recorded additions remain physically unknown,
and rescued pairs must be compared with the full same-receiver application
inventory at the existing 2 microsecond/8 kHz identity tolerances. Correct
visit-level presence cannot substitute for receiver timing and frequency
identity.
