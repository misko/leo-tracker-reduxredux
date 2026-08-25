# Response-blind Doppler holdout feasibility

**Date:** 2026-08-25

**Dataset phase:** post-refill-fix, counter-authoritative, protocol-unopened holdout

**Result:** **launch gate failed: 4 of 15 captures were evaluable; 10 were required**

## Executive result

The proposed greater-than-or-equal-to-10-capture holdout comparison must not be
launched on this cohort under the frozen protocol. All 15 allowlisted captures
provided a source-supported 1.495 s episode and about 1,120 complete 750 Hz
frame opportunities. Only four episodes met all predeclared even-Qin evidence
gates:

- `cap-20260825T022235-0afd1298f096`
- `cap-20260825T031521-ec8adc0e9426`
- `cap-20260825T033028-374381fbcd3a`
- `cap-20260825T043656-2da9e806d487`

This is a feasibility failure, not an estimator comparison. No future odd-Qin
response was demodulated or scored, and no fixed-500-ms, fixed-125-ms, causal
20-ms, or candidate state estimator was run. Consequently this report contains
no held-out CFO errors, rate errors, RMSE, or winner.

![Response-blind feasibility accounting](figures/2026_08_25_doppler_holdout_feasibility/feasibility-accounting.png)

The gray height is the complete frame-opportunity inventory. The colored height
is the supported even-Qin mask; green captures pass every frozen gate and red
captures do not. The 600-frame line is only one of four gates. In particular,
the captures with 711 and 708 supported frames still fail because their support
fractions are 0.635 and 0.632, below the frozen 0.65 requirement.

## Authority and freeze boundary

The dataset authority is the reviewed policy at commit
`2e17b4477b38494e14bab7ff39303cf3a219bb03`. The selector, contract, even-only
API, tests, and executable protocol were committed before reading any sealed
product or raw IQ byte at
`c6d0654aebd294745ef87416a5e5b5b503d17c01`.

This applies the cohort and leakage rules preregistered in the
[dataset-authority report](2026_08_25_doppler_experiment_dataset_policy.md). Its
POST-FIX interpretation follows the
[refill-aware method review](2026_08_25_doppler_rate_and_satellite_linking_method_review.md)
and the underlying
[24-hour post-refill retrospective](2026_08_25_post_refill_24h_retrospective/README.md).

The frozen inventory named exactly 15 `holdout_foundation` captures and required
at least 10 evaluable dispositions. Dynamic discovery, replacement captures,
newer captures, fallback after even-mask failure, and candidate-estimator runs
were disabled. Before any product or IQ access, the pass verified the actual
recording and Standard-analysis manifest bytes for all 15 captures against the
inventory and policy digests.

The pass inspected 60 manifest-declared path scopes and exactly 300 digest-pinned
scientific JSON products: five required Standard products per scope. It retained
780 trajectory-window audits (489 eligible and 291 rejected) and one selected
episode per capture. Every selected IQ stream was required to be complete,
device-counter anchored, one-segment, sample-loss observable, and free of gaps,
missing samples, overflows, enqueue failures, clipping, constant-IQ refills, and
terminal rejected continuity evidence.

Therefore these are **post-fix continuity-clean results**. The 11 failures below
must not be described as evidence of the old continuous-recording/refill defect.
They are failures of even-Qin signal support under this particular source-bound
episode and mask protocol.

## What was and was not sealed

The leakage boundary is deliberately precise:

- Frozen upstream Standard products selected the source observations, alias
  branch, trajectory, and frame epoch. Those products may contain all-Qin
  GLRT64 evidence. This conditioning is disclosed in both the protocol and the
  derived manifest; it is not claimed to be odd-Qin independent.
- The raw reader necessarily loaded a guarded full-frame IQ span. The new narrow
  API indexed and demodulated only zero-based even Qin positions 0, 2, ..., 298.
  Odd-time samples could be present in memory, but odd Qin symbols were not
  demodulated, scientifically evaluated, or scored.
- The persisted frame mask has only even-Qin CFO, uncertainty, exact coherence,
  roll-control coherence, margin, boundary, continuity, and rejection fields.
  Its strict schema forbids odd-response fields.
- Component tests prove invariance to odd-Qin-only sample perturbations and use
  spies that fail if the full all-Qin demodulator or even/odd split estimator is
  invoked.

Thus the future odd-Qin response remains unopened. The current result only says
whether the frozen training-side mask supplied enough support to justify the
planned comparison.

## Frozen selection and evaluability rules

| Stage | Frozen rule |
|---|---|
| Capture membership | Exact 15 `holdout_foundation` IDs; no substitutions |
| Required products | Path report v2, pilot scan v3, alias map v2, dealiased bank v4, final bank v3 |
| Source episode | Automatic-correction-eligible trajectory; exactly one raw source per canonical observation |
| Source window | 1,250--1,500 ms; at most 100 ms source gap; at least 25 observations |
| Source rank | Most observations, longest duration, highest median source margin, most evaluated probes, deterministic identity tie-breaks |
| Frame lattice | Counter-coordinate 750 Hz lattice; only complete guarded frames |
| Training fold | Zero-based even Qin symbols only |
| Residual search | +/-2,000 Hz around the frozen source/alias trajectory seed |
| Frame support | Exact coherence >=0.02, exact-minus-control margin >=0, and not on the search boundary |
| Episode gate | >=900 opportunities, >=600 supported, support fraction >=0.65, and >=75 consecutive supported frames |
| Cohort gate | >=10 evaluable captures |

All selected windows were 1.495 s. Fourteen used 60 source observations and one
used 58. Every selected upstream trajectory was degree one, although the
contract truthfully permits the upstream v3 bank's degree-one through
degree-three domain.

## Capture accounting

`Supp` is supported even-Qin frames, `Frac` is `Supp/Opp`, and `Run` is the
longest consecutive supported-frame run. Failure flags name every failed frozen
episode gate; they can overlap.

| Capture | Opp | Supp | Frac | Run | Disposition | Failed gates |
|---|---:|---:|---:|---:|---|---|
| `cap-20260825T010019-89c2889553e0` | 1120 | 0 | 0.000 | 0 | non-evaluable | supported, fraction, contiguous |
| `cap-20260825T015754-6bfe6b67b1be` | 1120 | 339 | 0.303 | 23 | non-evaluable | supported, fraction, contiguous |
| `cap-20260825T020035-c9413370f93b` | 1120 | 232 | 0.207 | 5 | non-evaluable | supported, fraction, contiguous |
| `cap-20260825T022235-0afd1298f096` | 1121 | 1111 | 0.991 | 997 | **evaluable** | none |
| `cap-20260825T030000-49e936766343` | 1120 | 562 | 0.502 | 516 | non-evaluable | supported, fraction |
| `cap-20260825T031245-4fbc260ab065` | 1120 | 281 | 0.251 | 11 | non-evaluable | supported, fraction, contiguous |
| `cap-20260825T031521-ec8adc0e9426` | 1120 | 1120 | 1.000 | 1120 | **evaluable** | none |
| `cap-20260825T033028-374381fbcd3a` | 1120 | 1118 | 0.998 | 1056 | **evaluable** | none |
| `cap-20260825T033302-80fddf217eb5` | 1120 | 711 | 0.635 | 238 | non-evaluable | fraction |
| `cap-20260825T034929-bc0480bdb4a8` | 1120 | 491 | 0.438 | 23 | non-evaluable | supported, fraction, contiguous |
| `cap-20260825T035201-d0abaead734c` | 1120 | 526 | 0.470 | 459 | non-evaluable | supported, fraction |
| `cap-20260825T041207-a5f08ab5bd42` | 1120 | 692 | 0.618 | 600 | non-evaluable | fraction |
| `cap-20260825T043656-2da9e806d487` | 1121 | 874 | 0.780 | 291 | **evaluable** | none |
| `cap-20260825T050946-ab916a6d0eee` | 1120 | 708 | 0.632 | 393 | non-evaluable | fraction |
| `cap-20260825T051221-0032700e2140` | 1120 | 589 | 0.526 | 66 | non-evaluable | supported, fraction, contiguous |

Across all captures there were 16,802 opportunities and 9,354 supported frames,
an aggregate support fraction of 0.557. Aggregation does not override the
per-capture gates. Eleven captures failed the support-fraction gate, eight also
failed the 600-frame absolute-support gate, six also failed the 75-frame
contiguity gate, and none failed the opportunity-count gate.

Unsupported rows reported 7,448 occurrences of exact coherence below 0.02,
2,236 occurrences of a non-positive exact-minus-control margin, and 388 search
boundary hits. Reasons overlap within a frame, so these totals must not be added
to infer a unique rejected-frame count. Low exact coherence was the dominant
training-side rejection mechanism.

## Interpretation and next decision

The source-side selector itself was feasible: every capture supplied a selected
episode and every episode supplied more than 900 complete frame opportunities.
The cohort gate failed later, because the even-Qin evidence was not sufficiently
dense and persistent in 11 captures. This distinction matters: there is enough
counter-contiguous recording duration, but not enough qualified frame evidence
under the frozen mask to support the requested greater-than-or-equal-to-10
comparison.

The closest failures were `033302` (0.635), `050946` (0.632), and `041207`
(0.618). Those observations are diagnostic only. Relaxing the threshold now and
calling the same analysis predeclared would be post-selection. A revised
protocol could still preserve the unopened odd response, but it must be labeled
as a new, feasibility-informed protocol and should preferably be tuned on a
separate development role before it is used for confirmatory claims.

The clean next options are:

1. Stop this holdout lane as designed and use the four passing captures only for
   explicitly underpowered smoke testing, not the promised >=10-capture result.
2. Diagnose even-Qin acquisition/support on policy-authorized development data,
   freeze a justified source/mask revision, and apply it to a genuinely unopened
   holdout cohort.
3. Add more separately authorized, counter-authoritative, protocol-unopened
   captures to a new frozen holdout policy. Do not substitute them dynamically
   into this failed run.

No option requires revisiting the old refill-affected data, and this result does
not authorize opening the sealed odd-Qin response in the 11 failed captures.

## Reproducibility and artifacts

The frozen run completed in 84.495 s. The machine-readable evidence is:

- [Derived manifest](figures/2026_08_25_doppler_holdout_feasibility/derived-manifest.json)
  (11,510,453 bytes; file SHA-256
  `sha256:860b067a154b6b5ecf3172aa2f18105d4ef753cdb5472bab44cbfe9339662c70`;
  semantic manifest digest
  `sha256:c82a548683cbdfd026420ace9c8b6161ba5b69331682d6c68c1baafd73410b39`)
- [Failure ledger](figures/2026_08_25_doppler_holdout_feasibility/failure-ledger.csv)
  (SHA-256
  `sha256:bae08e36a159362cf78fec3036ad0015ecdac29475e73c39b7bd3e79ad7a51d9`)
- [Accounting PNG](figures/2026_08_25_doppler_holdout_feasibility/feasibility-accounting.png)
  (plain Matplotlib, 2295 x 935; SHA-256
  `sha256:9c742816a22df2214af9a6e272e2a2db589c9df2908252e8443ba64eb2bbf914`)
- [Artifact manifest](figures/2026_08_25_doppler_holdout_feasibility/artifact-manifest.json)

The derived manifest additionally binds the dataset-policy bytes, frozen
inventory, protocol configuration, selector implementation, even estimator,
manifest contract, every actual recording/analysis manifest, all 300 inspected
product receipts and document digests, all inspected scopes and source-window
digests, each selected source/alias trajectory, and every retained frame-mask
row.

## Related reports

- [Dataset authority for the next Doppler experiments](2026_08_25_doppler_experiment_dataset_policy.md)
- [Refill-aware Doppler-rate and satellite-linking review](2026_08_25_doppler_rate_and_satellite_linking_method_review.md)
- [Post-refill 24-hour retrospective](2026_08_25_post_refill_24h_retrospective/README.md)
