# TG11 decision-detector diagnostic dataset plan

Status: design only. No generator has been written, no IQ has been materialized,
and no detector outcome has been evaluated. Existing controls, golden fixtures,
source locks, thresholds, and results remain unchanged.

## Motivation and limits of the phase-one discrepancy

The second 2.5 MS/s phase-one visit is not physical negative truth. The current
ten-candidate application produced no passing pair and had a largest margin of
0.016678. TG11 produced an RX0 pair in probes 4 and 10, near -86.1 kHz, with
margins 0.095757 and 0.114112. Neither observation associated to the application's
110 sub-threshold RX0 candidates within 2 microseconds and 8 kHz; the nearest
application candidates differed by about 122 samples and 84.7 kHz. These facts
are recorded in `../tg11/PHASE1_REPORT.md` and
`../tg11/phase1_cost_results.json`.

That pair is an **unadjudicated additional decision**, not a known false
positive. The recording may contain another physical signal, or the result may
come from a search or scoring difference. This dataset will use constructed
truth to distinguish those cases. It will not relabel the recorded visit.

One specific scoring difference needs direct coverage. The frozen native profile
defines `LEO_PRESENCE_GLRT_SYMBOL_DIVERSITY=1`; final scoring uses symbols 2--65
on even frames and 152--215 on odd frames (`presence.c`, lines 618--650). The
Python application GLRT-64 always selects symbols 2--65 (`pilot_methods.py`,
lines 490--521). Existing full-template pilots support both regions and cannot
isolate this difference. The new set therefore includes early-only, late-only,
and symbol-localized interference cases.

## Fixed corpus size and split

Materialize 52 physical 120 ms dual-receiver cases: 26 at 2.5 MS/s and 26 at
5 MS/s. Each rate has 13 development and 13 validation cases. Natural arrays
have dtype `<i2`, layout `sample_receiver_iq`, and shape
`(rate_hz * 120 // 1000, 2, 2)`. The raw payload is approximately 187.2 MB.

There is no holdout in this diagnostic set. Development may be used to debug a
new detector architecture. Once a variant and every decision rule are frozen,
validation is run once. Validation arrays, margins, and detector results must
not be opened during development. A failed validation is reported without
changing seeds, amplitudes, thresholds, or membership.

For each `(split, rate)` the 13 physical cases are:

| Cohort | Physical cases | Receiver-level conditions |
|---|---:|---:|
| Analytic pilot-power ladder | 4 | 8 |
| Stationary adversarial controls | 5 | 10 |
| One four-visit causal sequence | 4 | 8 total receiver observations |

Case IDs use
`tg11diag-{dev|val}-r{2500000|5000000}-{cohort}-{ordinal}`. Ladder and
stationary cases alternate lower and upper edges. Each four-visit causal sequence
keeps one edge, channel, session and tuning identity so cache reuse is possible.
The development and validation sequence use opposite edges within each rate;
the 2.5 MS/s development sequence is lower and the 5 MS/s development sequence
is upper, with validation reversed. The complete membership covers both edges,
rates, receivers, and splits; sequence edge is intentionally not crossed within
one causal key.

Noise seeds are fixed without detector feedback:

```text
seed = split_base + rate_index * 100000 + case_ordinal * 10 + receiver
split_base: development=73000000, validation=97000000
rate_index: 2.5 MS/s=0, 5 MS/s=1
```

Every receiver/case has a unique noise seed. Development and validation share
the reviewed canonical pilot template intentionally, but share no noise vector,
oscillator phase, timing origin, or channel phase.

Use exact integer source-counter bases above `2**53`:

| Split | Rate | Counter base |
|---|---:|---:|
| development | 2.5 MS/s | 9,100,000,000,000,000 |
| development | 5 MS/s | 9,200,000,000,000,000 |
| validation | 2.5 MS/s | 9,300,000,000,000,000 |
| validation | 5 MS/s | 9,400,000,000,000,000 |

Sequence visits advance by exactly `rate_hz * 120 // 1000`; stationary cases
use non-overlapping counter intervals. Continuous CFO phase is calculated from
the exact rational counter modulo one cycle before conversion to floating point.
Fractional frame timing is kept as an integer counter plus a signed fractional
sample, never as one large float.

## Construction contract

Use `leo.analysis.starlink.templates.qin_edge_pilot_frame`, pinned by source and
template SHA-256. Generate the physical 750 Hz frame lattice with
`rate_hz / 750` represented as a rational. Apply fractional delay to each
zero-guarded canonical frame by the existing reviewed bandlimited-shift method,
then apply continuous CFO and the receiver channel. Do not construct a pilot
from a sinusoid or repeat one rounded discrete frame.

Each receiver has independent complex Gaussian noise. The default channel is a
flat complex scalar with a predeclared phase; signal amplitudes are normalized
at the receiver input, so receiver gain does not silently change a requested
power stratum. All component oscillators have absolute counter-referenced phase.
Quantize real and imaginary components independently with round-to-nearest-even,
then clip to CI16. Any clipped component fails dataset construction.

For every component record its pre-quantization mean power, complex noise power,
power-over-noise ratio, peak, phase, CFO or tone frequency, channel coefficient,
frame coordinates, injected interval, and supported OFDM-symbol ranges. Record
the final per-receiver peak and clipping count.

The generator may reuse the algorithms in `../lag3_controls/build_controls.py`,
but the new design, seeds, arrays, and manifest are independent. It must not
import a detector, evaluate a score, or search amplitudes based on an outcome.

## Analytic pilot-power ladder

Each split and rate has four ladder cases. The two receivers carry different
fixed target ratios, giving this eight-point ladder in dB:

```text
[-30, -24], [-18, -12], [-6, 0], [6, 12]
```

The pair in each bracket is `(RX0, RX1)` for one physical case. For a generated
unit-amplitude pilot train `u`, flat channel `h`, and complex noise power
`P_noise`, calculate the amplitude before IQ generation as

```text
A = sqrt(10**(target_db/10) * P_noise / mean(abs(h*u)**2))
```

This fixes input power analytically. The values do not assume a detector margin
or use the prior 0.849 minimum control margin. CFO, fractional timing, channel
phase, and noise are predeclared independently in each split; the four ladder
cases alternate edges and include zero CFO, moderate signed CFO, off-grid CFO,
and one value near each signed 400 kHz search boundary.

The fixed application margin remains `>= 0.025`. After evaluation, report every
exact score, control score, margin, association, and active decision against the
analytic power coordinate. A split is informative about the operating boundary
only if its frozen ladder contains at least one application margin below 0.025
and one at or above 0.025 at each rate. Failure to bracket is a reported dataset
limitation; it does not authorize adding levels or moving amplitudes.

No ladder row is assigned an expected detector-positive label. Pilot presence is
physical construction truth. Sensitivity and contract agreement are separate:
an inactive pilot is a constructed miss, while a candidate decision that differs
from the current application is a contract difference even when it correctly
associates to the injected pilot.

## Stationary adversarial controls

Each split and rate contains the following five physical cases, with fresh seeds
and phases in validation:

1. **Noise family.** RX0 is white complex Gaussian noise. RX1 is independently
   seeded complex AR(1) noise with coefficient 0.85, normalized to the same mean
   power. Neither contains a pilot, tone, or copied real IQ.
2. **Narrowband nuisance family.** RX0 contains one off-grid tone. RX1 contains
   five unequal-amplitude off-grid tones with fixed signed frequencies and
   phases. Total nuisance-to-noise power is +18 dB. Neither contains a pilot.
3. **Multiple-hypothesis family.** RX0 contains two equal-power pilots separated
   by more than 8 kHz CFO and more than 2 microseconds timing. RX1 contains one
   pilot plus a stronger five-tone interferer. The truth lists every component;
   either complete pilot trajectory may be selected on RX0, but mixing one
   trajectory's first observation with the other's second observation fails.
4. **Symbol-region support family.** RX0 contains only canonical pilot symbols
   2--65 in every frame. RX1 contains only symbols 152--215. All other samples
   of the pilot contribution are zero before noise is added. These are deliberate
   partial-known-region controls, not claims of complete Starlink frames.
5. **Symbol-region interference family.** Both receivers contain a full canonical
   pilot. RX0 receives a strong off-grid tone burst only over symbols 2--65;
   RX1 receives the fixed multitone burst only over symbols 152--215. Burst masks
   use the same rounded symbol boundaries as the template construction and are
   recorded per frame.

The two pilot-bearing stationary cases use analytic received pilot power of
+6 dB. The equal-power two-pilot case uses 0 dB per pilot. Nuisance amplitudes
are determined from the declared noise power, not a detector result.

The region controls are evaluated in two views. The application and candidate
retain their frozen production symbol selections; a truth report records which
selected regions actually contain injected support. Results must be reported
separately for early-only, late-only, early-interfered, and late-interfered rows.
These cases diagnose a scoring-contract difference; their active state is not
predeclared from either implementation.

## Four-visit causal sequences

Each `(split, rate)` has one fresh four-visit sequence. Arrays are newly generated
for every visit with independent noise. Nothing is implemented by relabeling or
repeating an earlier array. Both receiver streams advance under their own full
cache key, and edge, channel, session and tuning identity stay constant through
all four visits.

RX0 exercises fading, disappearance, and reacquisition:

1. pilot A at +6 dB;
2. the same physical trajectory at -6 dB, with continuous timing and CFO;
3. no pilot, with independent colored noise and the declared multitone nuisance;
4. pilot B at +6 dB, shifted by 12 microseconds and 40 kHz from A's extrapolated
   trajectory.

RX1 exercises drift, wrong-track rejection, and ambiguity:

1. pilot A at +6 dB;
2. A advances by a predeclared 1 microsecond timing drift and 4 kHz CFO drift;
3. pilot B replaces A beyond both innovation gates: 12 microseconds and 40 kHz;
4. A and B are both present at 0 dB per trajectory with distinct timing and CFO.

The development and validation sequences use different initial epochs, signed
drift directions, carrier phases, and noise seeds. Drift is a piecewise-constant
stress model: timing and CFO change at visit boundaries and remain constant within
each 120 ms visit. Carrier phase is integrated across a frequency change while a
named trajectory persists. A replacement trajectory has its own explicitly
declared phase origin; the data does not claim smooth within-dwell Doppler.
Truth is derived from absolute source coordinates for each visit. An active output must associate both fresh
members to one currently injected trajectory. A stale A decision during RX0
visit 3 or RX1 visit 3 fails truth even if its margin passes. RX0 visit 3 is a
constructed negative and must remain inactive. RX1 visit 4 may select A or B,
but a hybrid pair fails.

Route counts are diagnostic until the rank-screen coordinate is separately
qualified. In particular, this corpus must not define a guided-route success by
loosening the frozen 4-microsecond innovation gate or calibrating it from these
outcomes.

## Manifest and immutable artifacts

The eventual `cases.json` should be an object with `schema`, `design_sha256`,
`source_lock_sha256`, `membership_sha256`, and ordered `cases`. Each case records:

```text
case_id, split, cohort, rate_hz, edge, channel,
sequence_id|null, sequence_index|null,
source_start_counter, source_end_counter,
raw_npy {path, dtype:"<i2", shape:[N,2,2], sha256},
receivers[2] {
  noise, channel, components[], analytic_power_coordinates,
  constructed_negative, ambiguity
}
```

Pilot components include `trajectory_id`, edge, CFO, exact integer-plus-fraction
epoch origin, every physical frame coordinate, supported symbol ranges, amplitude,
power, and absolute phase convention. Tone components include all frequencies,
amplitudes, phases, and symbol-region masks. Truth metadata contains no detector
score, rank, margin, route, or expected threshold outcome.

Before materialization, freeze the design, generator, canonical template source,
and seed/membership table in `source_lock.json`. After materialization, add every
IQ hash and the manifest hash without evaluating a detector. Large `.npy` files
belong in `.gitignore`; manifests, generator, source lock, and component tests are
reviewable artifacts.

## Required construction tests

Component-owned tests should verify:

- exact case count, ordering, split/rate/edge/RX coverage, and unique seeds;
- dtype, shape, layout, source-counter extent, file hash, and manifest digest;
- no array or noise seed reused across development and validation;
- no clipping and agreement between stored and recomputed analytic powers;
- rational 750 Hz frame lattice, fractional-delay convention, and continuous
  counter-referenced CFO phase across sequence visits;
- exact early/late symbol masks and localized nuisance masks before quantization;
- negative cases contain no pilot component and multi-hypothesis cases retain all
  independent truth trajectories;
- causal sequence counters are contiguous and truth never refers to a future
  visit; and
- association operates on integer source counters plus fractional samples and
  requires two actual, non-overlapping, currently supported observations from one
  trajectory.

## Evaluation and reporting contract

Run the frozen current application and one frozen candidate on development.
Report, by split/rate/cohort/RX, physical-truth association, application/candidate
active state at margin 0.025, exact/control scores, misses, additions, lost
decisions, selected trajectory, timing/CFO errors, and routes. Do not collapse
the following categories:

- candidate addition associated to an injected pilot: truth-supported additional
  sensitivity and an application-contract difference;
- candidate addition on constructed noise/tone/multitone: constructed false
  positive;
- candidate addition on recorded unlabeled IQ: unadjudicated additional decision;
- active hybrid of two injected trajectories: association failure; and
- inactive low-power pilot: constructed miss, reported at its analytic power.

Freeze the candidate and analysis code before opening validation. Validation uses
the same 0.025 margin, 2-microsecond timing, 8-kHz CFO, same-receiver, and
non-overlap rules. A 10x cost claim still requires complete paired whole-decision
timing on a separate frozen real-IQ evaluation. Synthetic results establish
controlled sensitivity and specificity; they do not establish field prevalence,
a field false-alarm rate, or physical truth for the phase-one recorded extra.
