# Same-source CFO fragment audit

Repeated fragments of the same training-selected physical source usually have
disjoint time support and substantially more coherent offsets than unrelated
sources on the same receiver and exact RF.  This supports one narrow next test:
a **robust soft CFO coupling for disjoint same-NORAD fragments within one scan,
receiver and exact RF**.  It does not support a hard common offset, and it does
not support coupling receivers.

## Frozen question and method

This is a training-only replay at the 32 qualified original IID endpoints.  It
does not fit a position and does not read reference errors or held observations.
For every track, the original Student-t4, scale-100 Hz profiler supplies the CFO
of the training-MAP visible candidate.  A physical identity is admitted only
when that candidate's normalized within-track posterior is at least 0.90, as in
the frozen source-balance diagnostic.  The grouping key is scan, selected NORAD,
exact RF and receiver.

Offsets in the likelihood are normalized to 11.2 GHz.  The audit converts them
back to native frequency by multiplying by `RF / 11.2 GHz`, then compares them
modulo the GLRT alias period `1 / 4.4 us = 227272.727... Hz`.  This prevents an
integer pilot alias from appearing as physical CFO disagreement.

Track pairs are classified from training support alone:

- `shared_visit` means at least one identical GLRT visit and is treated as a
  likely alternative-track or duplicate-evidence case.
- `interval_overlap_no_shared_visit` means the time ranges overlap without an
  identical visit.
- `disjoint` means one training range ends before the other begins and is the
  only class that can add a long time lever arm.

The descriptive control is a different selected NORAD in the same scan,
receiver and exact RF, matched within support class to the nearest gap, overlap
and combined span.  Matching is deterministic and with replacement.  The
controls are close in gap (disjoint median absolute mismatch 1.71 s) but less
close in full span (median 10.94 s), so the paired comparison is evidence about
CFO specificity rather than an inferential test.

## Result

Of 1,923 tracks, 1,887 pass the identity threshold and 36 remain explicit
ambiguous exclusions.  No candidate list contains a duplicated NORAD.

There are 98 repeated same-source/same-receiver groups, each represented by one
track pair.  Seventy-six pairs are disjoint and 22 share training visits; none
merely overlap without a shared visit.  Every pair uses the same receiver
channel.  Thus the usable support is mostly fragmented rather than simultaneous:
the disjoint pairs span a median 57.64 s, with a median 2.66 s gap.

For the 76 disjoint pairs, the absolute alias-wrapped native CFO disagreement is
338.03 Hz median, 1,273.49 Hz P90.  The distribution has a real tail: 52/76 are
within 500 Hz, 65/76 within 1 kHz, 72/76 within 2 kHz, while the two largest are
38,997 and 97,507 Hz.  All 76 have a matched different-source control.  The
within-source disagreement is smaller in 66/76 cases; matched controls have
3,659.07 Hz median disagreement over all support classes, and the median paired
`control - within` difference for disjoint pairs is 2,300.16 Hz.

The 22 shared-visit pairs are consistent with alternative GLRT tracks rather
than independent repetitions: all are same-channel and share visits, and four
have CFO disagreements above 20 kHz.  They should not increase effective sample
size or drive a sharing constraint.

Across receivers, the same selected source has about an order of magnitude more
offset disagreement: 11,048.10 Hz median for 85 disjoint pairs and 10,378.01 Hz
for 519 shared-visit pairs.  Receiver paths therefore require separate CFO
effects.

## Decision and next test

The feasibility test passes for **soft, robust, same-receiver coupling on the 76
disjoint pairs only**.  A lean screen can retain the original independent t4
observation likelihood and candidate mixtures, then add a heavy-tailed
same-source CFO-difference term in native frequency with a predeclared scale in
the observed 0.5--1 kHz range.  Candidate identity and disjoint support must be
frozen from the original training endpoint.  The coupling must be alias-aware,
must exclude shared-visit tracks, and must never cross receivers.  Because four
disjoint pairs exceed 2 kHz and two are tens of kilohertz apart, exact sharing or
a narrow Gaussian constraint is contradicted by these data.

This is conditional evidence.  The selected NORADs are not independently
verified identities, and position/timing error can itself shift profiled CFOs.
The audit establishes a plausible regularizer and long lever arm, not a location
improvement.

## Reproduction and provenance

[`run.py`](run.py) is the executable replay and [`test_run.py`](test_run.py)
covers native alias wrapping, the three support cases and deterministic
same-class control matching.  Three tests pass.  The single-thread replay took
18.2 seconds under a 90-second cap.

[`results.json`](results.json) contains all 1,923 track rows, all repeated-source
pairs, their matched controls, cross-receiver pairs, aggregate counts, and SHA-256
bindings for the exact plan, every original IID result, both baseline adapters,
the physical-identity sidecar, and the prior lane-offset model and protocol.  Its
embedded audit-script digest matches the saved executable.  No IQ, RF collection,
archive write, held residual or position reference was used.

The older [`measurement_audit`](../measurement_audit/README.md) and
[`orbit_age_audit`](../orbit_age_audit/README.md) were produced by bounded inline
replays before executable preservation was requested.  Their exact inline source
is no longer present in this agent's retained context, so it was not reconstructed
or represented as an exact replay script.
