# Receiver-order sequence-design audit

## Decision

A bounded next stage is scientifically feasible only as a **candidate-consistent
receiver-order proxy**.  It can describe which receiver first produced a
candidate compatible with a frozen Doppler hypothesis.  It cannot establish
satellite identity, physical signal arrival order, beam response, or receiver
clock delay.

The training forecast bank is deliberately in canonical normalized-frequency
coordinates, while the public detector publishes native, absolute
baseband-coordinate `fractional_tracking_cfo_hz`.  A raw future candidate is
therefore ineligible until a training-only, lane-specific inverse mapping is
available.  Do not substitute an RF-scale rule across channels or edges.

## Coordinate and lane contract

For a public trajectory lane with exact key

```text
(session_id, channel, edge, receiver_id, actual_rf_hz)
```

the installed trajectory convention is

```text
normalized_hz = (11_200_000_000 / actual_rf_hz)
                * (native_tracking_cfo_hz
                   - alias_index * 227_272.72727272726)
```

The alias index is an integer attached to a training reconstruction decision;
it is not recoverable from a future candidate and forecast residual alone.
`actual_rf_hz` is the attested tuner RF center, while the detector's native CFO
already includes the pilot-to-tuner centering.  This is why multiplication by a
new channel or RF scale is insufficient to transfer a raw candidate between
lanes.  The existing lane-continuity correction explicitly classified a
channel-2 versus channel-3 comparison inapplicable for this reason.

The mapping artifact must be built solely from training probes and export, for
every selected forecast track, its full exact lane key, source-observation
bindings, native CFO, normalized CFO, and integer alias anchor.  It must also
prove that every training observation used by that track has that lane key.
Any mixed-lane track, missing raw anchor, nonfinite CFO, duplicate binding, or
unknown alias makes that forecast track ineligible.  The future join is allowed
only when the future opportunity has the same session, channel, edge, and
`actual_rf_hz`; the receiver is intentionally allowed to differ only after the
receiver-offset gate below passes.

This conclusion is independently supported by the installed-source audit:
trajectory reconstruction groups by channel, edge, receiver, and actual RF;
scales both native CFO and alias spacing to 11.2 GHz before de-aliasing; and
passes the result as the public track measurement.  Each forecast-bank
`predicted_hz` already includes its track-candidate's frozen profiled training
CFO, so it is the complete expected normalized coordinate for matching:

```text
expected_track_hz(t, candidate) = predicted_hz(t, candidate)
```

No held measurement may choose or update that profiled CFO.

## Frozen future-match rule

For each frozen top-three hypothesis, visit every eligible later opportunity
with that exact non-receiver lane key and a visible forecast.  Retain every
such opportunity before reading its candidates.  A qualified receiver with no
passing detector candidate is a `no_matching_candidate` opportunity.  A missing
or duplicate receiver probe, unqualified input/timing, unavailable timestamp,
or malformed candidate is `missing_or_invalid`, not a nondetection.  Invisible
forecasts and lane-mismatched opportunities are `out_of_scope`, also not
nondetections.

For every passing raw candidate, use the training-anchored lane transform and
compute a residual wrapped at that lane's normalized alias period.  Represent
the result as the wrapped residual plus an unresolved integer alias, rather
than enumerating an unbounded set of aliases or selecting one that minimizes a
held residual.  A fixed 2,500-Hz canonical residual gate is acceptable only as
the predeclared existing trajectory tolerance; it is far below half of the
roughly 227-kHz native alias spacing after normalization.  A passing row is
`alias_equivalent`, not an alias-resolution result.

The matching code must freeze its tie handling before execution:

* one raw candidate may support at most one row for a given frozen hypothesis
  and receiver/window;
* multiple compatible raw candidates in that row are `ambiguous_candidate`,
  unless their public candidate identities are documented aliases of the same
  detector event;
* compatibility with more than one frozen track or top-three satellite at the
  same receiver/window is `ambiguous_hypothesis`, excluded from order summaries;
* an accepted proxy hit records the wrapped residual, unresolved alias state,
  source identity, detector rank and margin.  It does not carry a decoded
  satellite label.

The residual threshold defines the event, so held residual distributions,
match counts, and gate pass rates are descriptive diagnostics only.  They are
not an independent held-frequency validation and cannot be used to adjust the
gate, aliases, channel relation, candidate ranking, or offsets.

## Receiver-offset gate

A receiver offset is a calibration parameter, not an opportunity to make
future data agree.  A public track is fixed to one receiver, so its counterpart
receiver's raw candidate cannot be asserted to be bound to that same track.
Estimate a weaker, training-only paired-candidate **proxy** per exact
`(session, channel, edge, actual_rf_hz)` key: epoch-compatible paired training
windows, frozen alias wrapping, and the predeclared robust location of
`native_rx1 - native_rx0`.  This is an empirical receiver-coordinate
calibration assumption, not proof that the two candidates share an emitter or
satellite.  Retain every contributing paired-window candidate identity, native
alias state, and residual; future matching must not promote the proxy into a
shared-target claim.

Permit transfer of that offset to future receiver matching only when all of the
following are true:

1. at least 10 distinct paired training source windows contribute;
2. both receivers are qualified and their timestamps/counters form a compatible
   pair (the existing proposed `<= 2.2 microseconds` bound may be used if it is
   checked before residual fitting);
3. the estimator and its sign convention are fixed, and the pairwise MAD is at
   most 2,500 Hz in native receiver-CFO units;
4. no contributing source window is outside `train`, and none is reused as a
   later target or reception-conditioning observation; and
5. the resulting bias, count, MAD, exact lane key, anchor digest and training
   partition digest are persisted before any later matching.

If calibration is unavailable or fails, do not silently use zero offset and do
not borrow an offset across RF, channel, edge, recording, or receiver.  Mark
the cross-receiver result unavailable.  A same-receiver sequence may still be
reported if its own raw-to-track mapping passes.

## Sequence endpoint and interpretation

Build receiver sequences separately for each frozen track–candidate hypothesis
and later role.  The first accepted proxy hit time per receiver is an interval
censored observation: it is **left-censored** when the receiver is already a
hit in the first eligible opportunity, **right-censored** when it has no hit by
the last eligible opportunity, and tied when both receivers first hit in the
same paired source window.  An ordinary lag is reported only when both first
hits are observed and occur in distinct ordered windows.  Its timing precision
is bounded by the paired opportunity schedule and source timing, not by the
fractional detector epoch alone.

The reception period may condition a later fixed hypothesis only through
quantities frozen from training.  It must not choose an identity, alias,
offset, gate, first endpoint, or receiver direction that is then scored in the
held-frequency period.  A reception-derived direction can be displayed as a
separate exploratory descriptor, but it is not transferred as truth or used to
select held rows.  Receiver swap and trajectory-time reversal remain required
negative controls; they diagnose coding asymmetry and schedule effects and do
not confer physical direction.

The final wording must say “first candidate-consistent detector hit,” never
“first received,” “entry,” or “satellite arrival.”  Candidate probabilities are
training-conditional shortlist weights, and a passing proxy hit does not turn
them into identification confidence.

## Evidence reviewed

* `reports/2026_09_28_rx_training_forecast/README.md` and `PROTOCOL.md`:
  forecasts are training-derived, normalized-only, and explicitly lack raw
  matching anchors.
* `reports/2026_09_27_ds7_full88/FREQUENCY-REFERENCE-AUDIT.md`: installed
  public detector/trajectory coordinate trace and the tuner-center limitation.
* `reports/2026_09_27_ds7_wave2/cfo/LANE-CORRECTION.md`: documented rejection
  of cross-channel raw-CFO transfer without a frozen lane relation.
* `tools/rx_paired_opportunities.py`: opportunity statuses preserve missing and
  unqualified receiver states separately from an observed candidate absence.

## Completed-artifact outcome audit

Read-only audit of `alias-mapping.json`, `sequences.json`, `audit.json`, and
the matched-opportunity row count confirms that the completed artifacts follow
the bounded proxy contract.  The mapping contains 30 frozen tracks and 903
training alias points.  All 40 exact training calibration lanes qualified; the
smallest calibration support was 11 distinct training windows and the largest
recorded native-CFO MAD was 104.79 Hz, below the fixed 2,500-Hz native gate.

The sequence artifact contains 90 frozen hypotheses and two later roles per
hypothesis, hence 180 sequences.  Its 159,534 receiver-hypothesis rows equal
the JSONL line count and the sum of the reported status classes:

| Status | Reception | Held frequency | Total |
|---|---:|---:|---:|
| Unique hit | 131 | 49 | 180 |
| Ambiguous candidate | 549 | 153 | 702 |
| Ambiguous hypothesis | 3,433 | 93 | 3,526 |
| No matching candidate | 16,167 | 20,153 | 36,320 |
| Out of scope (lane mismatch) | 59,460 | 59,346 | 118,806 |

The audit reports 180 distinct unique raw candidate keys: none is counted as a
unique hit for more than one frozen hypothesis.  Endpoint accounting is 24
observed, 298 right-censored, and 38 earlier-ambiguity endpoints (360 receiver
endpoints total).  These totals support the stated collision and censoring
semantics; they are accounting evidence, not a detection-rate estimate.

There is exactly one uncensored lag: a reception-period, rank-one hypothesis
for catalogue number 69338 in `scan-fw-3ebf3526172258af`, where the recorded
proxy endpoint is RX0 then RX1 by 9.3431466 s.  Both endpoints are marked
observed without earlier ambiguity.  There is no held-frequency uncensored lag.
That hypothesis already has frozen conditional top-three probability 1.0, so
the hit and its lag cannot add candidate-selection or association-confidence
evidence.  The other 179 sequences are unavailable, tied, censored, or lack an
uncensored order.

Accordingly, the completed stage demonstrates only that the frozen coordinate
and ambiguity rules can produce a small number of candidate-consistent proxy
hits.  It does not demonstrate receiver direction, physical arrival order,
satellite identity, improved tracking confidence, or held-frequency predictive
improvement.
