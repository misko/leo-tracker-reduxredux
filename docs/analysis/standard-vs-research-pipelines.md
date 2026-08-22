# Standard and Research analysis pipelines

This document describes the two production analysis lanes applied to newly
committed, eligible dwells. Both lanes read the same immutable recording and run
the same contract-bound stage graph, but they use different known-pilot search
budgets and publish into disjoint namespaces.

Neither lane decodes a payload or establishes that a detected signal belongs to
Starlink. Their products remain candidate-only evidence.

## Routing at a glance

Every eligible dwell is assigned to exactly one lane before its receiver paths
are expanded into processing jobs:

```text
committed dwell + immutable manifest digest
                    |
                    v
 deterministic-manifest-bucket-v1
                    |
         bucket = digest mod 8
              /             \
       bucket 0          buckets 1..7
          |                   |
          v                   v
      Research             Standard
       dense                bounded
```

The assignment is deterministic rather than stateful randomness. The selection
digest binds the allocation epoch and recording manifest digest. Retrying or
reconciling the same dwell therefore produces the same bucket and lane. All
radios and receiver paths in a dwell follow that one assignment.

The production policy is one Research bucket out of eight. This is an
independent 1/8 probability for each uniformly distributed manifest digest; it
does not guarantee exactly one Research dwell in every consecutive group of
eight.

The persisted evidence needed to reconstruct the choice is:

- the run's `input_manifest_digest`;
- its persisted `pipeline_lane`;
- the pipeline release configuration, including allocation policy and epoch;
- the release configuration digest.

Existing published runs are never reassigned. Qualification, calibration and
acceptance captures remain excluded from automatic analysis.

## Profile comparison

| Property | Standard | Research |
|---|---:|---:|
| Automatic share | 7/8 expected | 1/8 expected |
| Product namespace | Standard kinds | `research.*` envelopes |
| Probe duration | 20 ms | 20 ms |
| Probe starts per 50 ms | 0, 25 ms | 0, 15, 30 ms |
| Probes per complete second | 40 | 60 |
| Residual-CFO domain | −400 to +400 kHz | −400 to +400 kHz |
| Coarse CFO step | 80 kHz | 10 kHz |
| Fine CFO radius / step | 80 kHz / 500 Hz | 10 kHz / 100 Hz |
| Conditioned radius / step | 2 kHz / 100 Hz | 1 kHz / 25 Hz |
| Retained and scored candidates | 10 | 32 |
| Candidates/probe entering residual Hough | 10 | 6 ranked; all 32 remain persisted |
| Candidate CFO separation | 10 kHz | 10 kHz |
| Candidate epoch separation | 5 samples | 5 samples |
| GLRT transform size | 512 | 4096 |
| Approximate GLRT residual spacing | 443.9 Hz | 55.5 Hz |
| Worker threads per receiver path | 4 | 2 |
| May replace Standard current analysis | Yes, within Standard lane | No |

The Research lane deliberately combines finer grids, more retained timing/CFO
basins, a longer GLRT transform and denser temporal sampling. It is intended to
measure what evidence the bounded Standard search misses, not to provide a
second automatic opinion on every dwell.

## Shared input

Both lanes receive:

1. A committed recording manifest and verified compressed-IQ closure.
2. One exact receiver-path binding containing stream, receiver, sample-rate,
   center-frequency, timing and calibration provenance.
3. The Qin known-pilot waveform for the selected Starlink edge.
4. A release-bound stage configuration whose digest becomes part of scientific
   lineage.

The recording store is read-only during analysis. Candidate searches operate on
independent probes; no neighboring probe, fitted trajectory or TLE prediction is
fed into initial acquisition.

## Known-pilot acquisition output

For each scheduled probe, acquisition searches timing and residual CFO, retains
a bounded set of separated local maxima and then refines and scores every
surviving candidate. Each candidate contains:

- local frame epoch;
- acquired and GLRT-refined tracking CFO;
- known-pilot exact score;
- wrong-pilot control score;
- exact-minus-control margin;
- candidate rank and bounded-inventory accounting;
- optional QAM diagnostics on the primary candidate.

The output is an inventory of hypotheses, not a track. Downstream association
may select at most one candidate from a probe when forming a time-coherent
track.

## Why Standard uses 10 candidates and 10 kHz / 5 samples

The T1 raw-IQ parameter study found that the former 80 kHz CFO and 20-sample
timing suppression distances could discard adjacent timing/CFO alternatives
before GLRT evaluation. Ten candidates with 10 kHz CFO and 5-sample timing
separation recovered 866 of 1,090 probes against the fixed straight-line audit,
versus 826 for the former Standard profile. Measured process CPU increased by
about 11.2 percent on that capture.

The change does not make the initial search trajectory-aware. Every probe still
performs its own full-range acquisition. It changes which local maxima survive
and raises the bounded number evaluated from eight to ten.

See the
[T1 search-parameter report](../../reports/2026_08_22_t1_glrt_search_parameter_study.md)
for the mechanism, ablations and limits.

## Scanner alignment

The live eight-edge scanner is a separate short-dwell detector, not a Standard
or Research full-dwell run. Its initial per-probe acquisition nevertheless uses
the same bounded search and basin-retention policy as Standard: a −400 to
+400 kHz residual-CFO domain, 80 kHz coarse steps, 80 kHz / 500 Hz fine
refinement, ten retained candidates, 10 kHz candidate-CFO separation and
5-sample epoch separation. Each 20 ms probe remains independent.

Before this alignment, the scanner already used Standard's CFO domain and
refinement grids, but retained only eight candidates and applied the older
80 kHz / 20-sample nonmaximum-suppression distances. That could discard nearby
timing/CFO basins before GLRT-64 evaluation. The scanner still uses its own
two-probe confirmation rule and margin gate; this change does not turn its
candidate evidence into a satellite attribution or copy the dense Research
budget into the low-latency scanner.

## Why Research uses the dense profile

The dense profile is a measurement instrument for search loss:

- the 10 kHz coarse grid represents the acquisition surface more finely;
- 32 retained candidates preserve much more timing/CFO ambiguity;
- 100 Hz and 25 Hz refinement grids localize surviving basins more precisely;
- GLRT-4096 sharpens residual-CFO scoring;
- three probes per 50 ms sample time more densely.

On the T1 experiment, the same-probe dense acquisition took about 7.1 times the
former Standard wall time. The production Research schedule also contains 1.5
times as many probes. The exact deployed cost must therefore be monitored; the
1/8 allocation bounds frequency, not per-run cost.

Dense acquisition and residual-Hough segmentation have deliberately different
inventories. A complete 60-second Research dwell contains 3,600 independent
probes and up to 115,200 scored candidates. The immutable residual-Hough
implementation is bounded to 25,000 points. Research therefore persists all 32
candidates per probe in `research.pilot-scan`, then passes the lowest-rank six
per probe (at most 21,600 points) into line segmentation. The ranked-prefix
selection and full/selected/omitted counts are explicit in the version-3
alternate-track payload; it is not silent downsampling. Standard needs no
separate reduction because 2,400 probes times 10 candidates is 24,000 points.

The complete dense pilot-scan payload is about 89 MiB on the production
60-second corpus, compared with about 19 MiB for Standard. The durable JSON and
isolated-worker per-product safety bounds are therefore 128 MiB. This does not
relax the independent 512 MiB aggregate output limit for the path stage.

The ordinary `heavy` stage boundary is 30 minutes. Dense Research receiver-path
stages have a separate three-hour enforceable boundary because the measured
search cost cannot complete within the ordinary limit. This exception applies
only to Research `path-standard`; Standard paths and all radio/paired reducers
retain their ordinary resource-class boundaries. Attempts that exceed three
hours are still terminated without publishing partial products.

## Publication and promotion

Standard and Research products never share product kinds. Research wraps the
shared scientific payload in a definition-bound `research.*` envelope, and its
current-run pointer is independent from Standard's.

An automatically selected Research dwell runs Research **instead of** Standard.
It does not silently fall back to Standard on failure because that would bias
the sampled population and hide Research reliability problems. Operators may
explicitly request later reprocessing, but that is a new immutable run.

Research cannot promote products into the Standard lane. Presentation and API
readers must request the Research lane explicitly.

## Downstream trajectory safeguard

This acquisition change is compatible with the strict linear-only trajectory
work: candidate generation and scoring contain no polynomial-in-time model. The
lane configuration is persisted independently from downstream trajectory
configuration, so a release must bind both exact settings.

Until the versioned linear-only trajectory contracts replace the currently
published mixed-degree contracts, acquisition products must state their exact
configuration and downstream reports must not describe mixed-degree membership
as strict linear-only evidence.

## Pilot PNT Kalman research observable

The pilot-only PNT Kalman is an offline Research observable, not a Standard
product and not an automatic trajectory proposer. It consumes one bounded IQ
window that already has an independently acquired frame epoch, edge and CFO.
Every complete actual Starlink frame is measured separately from the known Qin
edge pilots.

Its continuous state is carrier phase, carrier frequency, carrier-frequency
rate, receiver-relative fractional-frame timing and timing rate. Carrier phase
is observed modulo pi, with a separate measured binary sign, because the
recorded pilot channel has two repeatable phase families separated by pi. The
timing state is a phase-ramp measurement across the eight edge tones; it is not
code phase, transmit time or pseudorange. The filter uses a constant-frequency-
rate transition, so frequency remains linear in time. It never fits an order-2
or order-3 frequency trajectory.

The output remains candidate-only. A wrong-pilot control, a declared phase-lock
qualification and comparison to independent frame-CFO measurements are required
before interpreting its carrier state. It cannot promote into Standard or claim
satellite identity, phase-continuous absolute carrier, range or position.

See the
[pilot PNT Kalman report](../../reports/2026_08_22_pilot_pnt_kalman.md) for the
verified-corpus evaluation and limitations.

## Operations and observability

Operators should monitor by lane:

- dwell and probe counts;
- candidate inventory and truncation counts;
- exact-minus-control margin distributions;
- candidate rank selected by later association;
- approximately 227.273 kHz alias jumps;
- CPU, wall time and memory per receiver path;
- queue latency, failures and rejected seals;
- final candidate-only track support and matched null controls.

A production release should be rejected if its persisted numerical
configuration differs from the values above, if one dwell creates automatic
runs in both lanes, or if retries produce a different assignment bucket.

## Rollback

Rollback changes the allocation policy for future newly registered dwells by
deploying a new release/allocation epoch. It does not rewrite completed runs or
their assignments. Setting the policy to disabled with numerator zero sends all
future eligible dwells to Standard while preserving Research history.

## Code map

| Concern | Authority |
|---|---|
| Acquisition configuration and validation | `leo.analysis.starlink.trajectory_feedback` |
| Standard production profile | `leo.analysis.standard.analyzers` |
| Research dense profile and namespace | `leo.analysis.research.analyzers` |
| Assignment policy and hashing | `leo.contracts.pipeline_lanes` |
| Automatic reconciliation routing | `leo.cli.processing` |
| Lane-specific worker registries | `leo.processing.service` |
| Independent lane catalog state | `leo.catalog.repository` |
