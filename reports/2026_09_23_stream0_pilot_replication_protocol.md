# Stream-0 whole-probe pilot replication protocol

Freeze population, implementation, protocol, and source hashes before IQ access.
The source model and seven comparisons are the unchanged stream-1 joint pilot
method. This tests conditional waveform replication, not association accuracy
or calibrated geometric phase. Metadata candidate detection has already used
IQ-derived GLRT scores; “held” refers to this replay's uninspected waveform
responses, conditional on that phase-blind candidate screen.

Use stream-0 of `cap-20260825T010019-89c2889553e0` and its existing run
`capture-34471d9087a94ec1b043951350de3956`. Include all ten probes with two
diagnostic components per receiver before timing qualification. Shuffle the
ascending sample starts using Python `random.Random(20260926)`; first five
are outer training, remaining five outer held. All receivers, components,
aliases, and controls of one probe stay together. Retain timing failures and
ambiguous matchings as abstentions, without IQ extraction. No time holdout.

Metadata receipt must bind the actual upper pilot edge, receiver scopes,
source-product hashes, recording manifest, and counter-timeline continuity.
Nominate the lowest candidate rank in each component of a unique
timing-compatible matching. No phase selects a source, alias, or opportunity.

For eligible probes read exactly 20 ms of saved dual IQ. Use the frozen eight
known-tone coefficients per source, nominal CFOs with ±2500 Hz residual grid
at 50 Hz, A,B,B,A updates, original rational frame synthesis, and all seven
models: exact pair, each single source, each single rolled source, both rolled,
and swapped epochs. No new controls, geometry, or shared-CFO fitting is added.

Each probe has local calibration samples: seeded random 100 microsecond groups,
16-sample guards, half calibration/half response. Inner seed is 20260925 plus
the probe's index in the full ten-probe chronological inventory. All models
and receivers share that physical split. Whole-probe outer holding tests
transfer of the frozen method **with local calibration**; it does not claim
prediction of an unseen probe without any probe-specific fitting. Only inner
calibration samples fit nuisance parameters. Outer held IQ is not opened until
all five outer training outcomes are sealed with hashes. Do not tune after
training; if implementation or authority fails, stop rather than silently alter
the method. The sealed method is identical for both partitions.

Report every probe's joint-minus-comparator prediction error and coverage.
Descriptive incremental support means lower response SSE than both nested
single-source models and every equal-capacity control, on both receivers.
This is not a calibrated significance threshold. Five outer held probes, with
possible abstentions and correlated same-capture signals, cannot support a
population-level orbit/position claim or precise confidence interval.

Each partition is bounded to five minutes and at most 100 ms capture duration.
Use verified read-only recording access. No new RF collection. Preserve the
entire population, held failures, source hashes, random groups, masks, nominees,
coefficients, and all model errors. No outcomes are used to redefine success.
