# Forecast and candidate-coordinate provenance

## Finding

I found no deterministic reception-versus-held transformation in the saved frequency coordinates.
Both roles use the same forecast generator, midpoint clock, lane scale, alias period, receiver-bias
correction, candidate gate, and dataset assembly path. The observed alignment collapse therefore
cannot be explained by an explicit role branch in these mappings.

There is one small timestamp-coordinate mismatch worth fixing in a residual-trajectory tool:
forecasts are evaluated at the grouped window midpoint, while each detected candidate has its own
projected support-center timestamp. The geometry dataset drops that support-center field. In the
actual calibration population the difference is only about -0.516 to +0.524 ms and has nearly the
same median in both roles, so it is not evidence for the observed role-boundary collapse. Exact
signed residual trajectories should nevertheless join the frozen opportunity artifact and either
forecast at candidate support center or export the offset explicitly.

## Forecast path

The grouped partition assigns a whole overlap-connected group to `train`, `reception`,
`held_frequency`, or embargo. The boundaries are fixed at 60% and 80% of the recording metadata
span; the role label does not alter a frequency value. The protocol explicitly makes later roles
forecast destinations only ([training forecast protocol](../2026_09_28_rx_training_forecast/PROTOCOL.md)).

The candidate-bank builder reads only the training-filtered public preparation. For each training
track and catalogue member, `rank_candidates` profiles one constant CFO as the mean of measured
minus predicted training frequency and ranks by training SSE
([rx_training_candidate_bank.py](../../tools/rx_training_candidate_bank.py)). It then constructs
one target-time vector containing both reception and held windows, with every time derived as
`window_midpoint_utc_ns - prepared.start_utc_ns`. A single prediction-bank call propagates all
selected catalogue members over that vector. Each exported prediction is

`tau-zero Doppler at 11.2 GHz + training-profiled constant CFO`.

The code uses the same expression for every target row. Visibility is the same forecast elevation
test (`elevation >= 0`) in both roles. Catalogue choice, top-three truncation, CFO fit, TLE snapshot,
site coordinates, and RF reference are fixed before either future role is inspected. There is no
future residual fit or role-specific time origin.

The geometry builder binds every forecast by exact source-window ID and requires its role and
prediction timestamp to equal the partition role and midpoint
([rx_geometry_dataset.py](../../tools/rx_geometry_dataset.py)). It reads the saved `predicted_hz`
unchanged for an RX0-anchored training track. For an RX1-anchored track it subtracts the lane's
training-only receiver bias after canonical scaling. The same adjustment is applied to all future
windows from that track.

## Observed-candidate path

The opportunity exporter obtains `fractional_tracking_cfo_hz` and
`passed_fractional_margin_gate` from each raw candidate and assigns no satellite ID
([rx_paired_opportunities.py](../../tools/rx_paired_opportunities.py)). Its candidate ID binds the
source window, receiver, rank, and detector fields. Grouping requires paired probes to agree on
channel, edge, sample counter, and actual RF; it does not select a candidate using a satellite
forecast.

The geometry builder retains every candidate whose existing fractional-margin gate is true. It
does not apply a forecast-residual gate. For receiver `r` and lane scale
`s = 11.2 GHz / actual_rf_hz`, the exported common coordinate is:

```text
RX0: canonical_rx0_hz = fractional_tracking_cfo_hz * s
RX1: canonical_rx0_hz = (fractional_tracking_cfo_hz - bias_rx1_minus_rx0_hz) * s
```

The alias period is the fixed raw spacing `1 / 4.4 us`, multiplied by the same lane scale. Later
alignment uses periodic distance, so no future integer alias is selected. The prediction adjustment
for RX1-anchored tracks and the observed RX1 adjustment use the same training-only lane bias and
scale.

The bias itself comes only from training candidates in the exact
`(session, channel, edge, actual_rf_hz)` lane
([rx_training_alias_mapping.py](../../tools/rx_training_alias_mapping.py)). Epoch-compatible RX
pairs are wrapped at the known raw alias period, one vote is retained per training window near a
fixed modal estimate, and qualification requires at least ten windows with MAD no greater than
2.5 kHz. The mapping stage filters the raw cache to training before projection and reconstruction.
No reception or held candidate can affect the scale, alias spacing, track anchor, or receiver bias.

## Direct checks on the frozen artifacts

The geometry dataset is cryptographically bound to the candidate bank, alias mapping, partitions,
and opportunity JSONL. Its 12 calibration lanes carry one constant scale, period, and bias per
lane across both roles. All 2,719 calibration windows bind the same source IDs and midpoint times
through the later temporal artifacts. The numerical checks below and their exact input hashes are
recorded in [provenance-receipt.json](provenance-receipt.json).

Joining the frozen dataset back to the opportunity candidate provenance gives these support-center
minus forecast-midpoint ranges:

| Role / receiver | Passed candidates | Range (ms) | Median (ms) |
|---|---:|---:|---:|
| Reception RX0 | 3,043 | -0.516 to +0.524 | +0.143 |
| Reception RX1 | 2,104 | -0.516 to +0.524 | +0.129 |
| Held RX0 | 1,803 | -0.515 to +0.522 | +0.145 |
| Held RX1 | 1,285 | -0.515 to +0.522 | +0.150 |

This sub-millisecond offset is present on both sides of the boundary with almost identical
medians. It should be preserved for exact trajectory work, but it is not a detected role-specific
clock discontinuity.

The detector-side population does change. Passed-candidate counts fall from 3,043 to 1,803 on RX0
and from 2,104 to 1,285 on RX1. Median fractional margin falls from about 0.499 to 0.399 on RX0 and
from 0.496 to 0.428 on RX1. Candidate-rank distributions remain broad in both roles. These facts
show a change in detector outputs under an unchanged gate; they do not establish why it changes or
which transmitter produced any candidate.

## Actionable residual-trajectory requirements

1. Preserve the exact lane, receiver, source-window ID, candidate ID/rank, and
   `(track_id, catalog_number)` forecast identity. Track ID alone is not a catalogue identity.
2. Rejoin `source_interval.support_center_utc_ns` from the frozen opportunity artifact. Report its
   offset from the saved midpoint and, if predictions are not recomputed at support center, keep
   that limitation visible.
3. Compute signed residuals on the saved canonical alias circle. Do not choose an integer alias,
   refit CFO/bias, or select a nominee using reception or held outcomes.
4. Retain all passed candidates and empty receiver windows. A nearest-candidate trajectory is
   selection-sensitive; separately report candidate count, rank, and margin so disappearance is
   distinguishable from a continuous residual.
5. Plot or summarize reception and held segments on one absolute UTC axis per lane. Do not reset
   time, unwrap frequency, or refit a slope at the role boundary.

The strongest concrete lead is the detector-output/support change, followed by testing whether any
individual saved nominee has a continuous signed residual approaching the boundary. It is not
evidence of a satellite handoff, and this provenance audit does not assign physical identity.
