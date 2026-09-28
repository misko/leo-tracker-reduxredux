# Dual-receiver beam-crossing feasibility experiment

User authorization: implement and test whether time-varying reception across
the nominally 20-degree-separated receiver axes adds satellite-tracking evidence.
SOL owns the model and tests; Terra audits inputs and geometry; the coordinator
freezes the executable comparison and evaluates the evidence. An independent
SOL review checks selection, controls and interpretation.

This note precedes new fits. Cohort membership, source hashes, executable model
parameters and the run command must be recorded in a separate frozen launch
specification before any evaluation outcome is read. This is not a claim that
the necessary input gates already pass.

## Scientific distinction

Existing directional models already evaluate predicted satellite direction at
observation times. A new temporal model must demonstrate information beyond that
baseline, not relabel the same rowwise east-direction feature. Nominal geometry
provides one directional contrast; receiver mapping, pointing, and beam response
remain insufficiently calibrated. Neither nominal tilt nor a smaller candidate
entropy establishes physical satellite identity.

The proposed extension compares changes in paired reception along each candidate
trajectory, including actual in-window contrast crossings when present. Missing
crossings remain missing. They must not be replaced by invented boundary events.
Detection order is a beam/visibility statistic, not inter-antenna RF propagation
delay. Receiver gain, correlated fading, transmitter behavior and observation
gaps remain alternative explanations.

## Mandatory input and interpretation gates

- Use existing cached derived evidence only; no new RF or raw-IQ reads.
- Bind source manifests, analysis products, opportunity timestamps, target/channel,
  sample rate, active dwell and receiver labels. Distinguish active dwell from
  the separate valid-visit field.
- Audit paired receiver windows and provenance overlap. Lack of an observation
  opportunity is missing data, not a non-detection.
- A detections-only track cannot supply an unbiased first detection, last
  detection or a four-category paired outcome including "neither". A conditional
  paired endpoint may support a narrower diagnostic, which must be labeled.
- Candidate identities and frequency offsets must be selected/fitted without
  using held reception outcomes or reference-relative position errors.
- Keep both receivers and overlapping source windows together in partitions.
  Randomize whole recordings for calibration/evaluation; record the seed and
  assignments before fitting. Existing research exposure remains disclosed.
- No model selection, orientation selection, threshold changes, membership
  replacement or deadline extension after seeing evaluation outcomes.

## Required comparison

Compare Doppler-only, existing directional reception, and explicit temporal
reception under identical source membership and candidate support. Controls must
preserve observation opportunities, channel/rate and receiver-pair dependence:
fixed-map receiver reversal, deterministic time reassignment, and trajectory
time reversal where meaningful. Do not destroy those invariants to manufacture
an easy negative control. If a control is mathematically equivalent to the model
or cannot identify the claimed effect, state that limitation.

Report held predictive performance, per-recording effects, source availability,
track/opportunity exclusions, actual crossing support, numerical failures and
resources. Downstream held-frequency prediction is the preferred association
endpoint. A reception-only feasibility result cannot substitute for it or for
geographic accuracy. Do not present the old 677 m pooled result as validation
of the new model.

## Execution envelope

One serialized numerical worker, one CPU/BLAS thread, nice 19, at most 4 GiB
address space and 300 seconds per declared bounded attempt. Input/feature work
and control scoring must be separately accounted for. Preserve failed attempts;
do not retry or expand scope automatically. Do not interfere with acquisition,
production analysis or unrelated concurrent research. No location search or
production deployment is authorized by this first feasibility experiment.

Pure model code must have component-owned tests for timing/mask alignment,
normalization, candidate identity consistency, nuisance cancellation, deterministic
controls and train/test separation. Original datasets, fixtures and historical
report seals remain unchanged.
