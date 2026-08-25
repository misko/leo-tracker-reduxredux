# Satellite identity recovery v2: same-emitter tracking without secure NORAD identity

Date: 2026-08-25 UTC

Experimental worktree: `codex/satellite-identity-recovery-v2`

## Outcome

The existing 150802 recording now supports **real same-emitter tracking across
RX0 and RX1**, and the strongest conditional catalog candidate remains
**STARLINK-31640 / NORAD 59748**. It does **not** support a secure NORAD
identity.

The positive and negative results are compatible rather than contradictory:

- the RX1-only arc is a precise, short Doppler-shape measurement for which
  59748 is much better than the next candidate under a narrow nuisance model;
- the RX0 raw-IQ replay registers the same local frame-bearing emitter on the
  second channel of the same Pluto;
- the alias-aware common-orbit audit then asks the harder identity question on
  the shared interval, allowing each receiver its own offset and bounded drift
  and requiring the orbit to beat receiver-local and shared-curvature radio
  nulls, remain interior and stable, and predict held-out data better than every
  catalog alternative;
- that harder test keeps 59748 as the training winner but fails the numerical
  identity gate.

The warranted consolidated claim is:

> **The receivers track the same real frame-bearing signal and its
> satellite-like Doppler structure. STARLINK-31640 / NORAD 59748 is the leading
> conditional candidate for the 150802 arc, but no NORAD object is securely
> identified.**

No new RF was collected. No production product, database row, recording, TLE
archive entry, or golden scientific fixture was changed. This experimental
branch adds report-only analyzers, component tests, and generated evidence over
the existing on-disk corpus; this consolidation file does not modify them.

## Frozen authority

The conclusions above are tied to immutable committed sources and byte-level
artifact hashes, not to the eventual commit that contains this synthesis.

| Evidence layer | Frozen authority |
|---|---|
| Last-ten recovery audit | committed report at `bbf84a06299ce5a9ea26d70e0d552eb58a3eaefa` (analysis parent `89e2e7636a407426e67474c7a2d12b073c1ef197`); report SHA-256 `040b53e81a4d1a1b0854d71710be837e374ffb1c37d567a04682f193e779110e` |
| 150802 RX1-only causal TLE comparison | committed report at `d63a12a11a18b6d3d6a9afd781f74e52d254cf2a`; report SHA-256 `64101c03eed2d55cff6fb27c688faa95efc381f35d73da2e18eb1d038776a942`; evidence SHA-256 `f7b9e0aa6c6b82aaabe3fd9c7af5786460810c481b4590381ddb88ff9d678bb5`; analysis-tool SHA-256 `b566fc98cd4a3afdc3c4c4d66dc51ff3ff177790ef08ebcb197355110c1f143f` |
| 150802 alias-aware common-orbit audit | report SHA-256 `943b0af869e6883ddc6d5245daf373c2f8bf5e86e7f35a53aa0224293e0e45ad`; evidence SHA-256 `a7bdc3ca474e502d6d94a9c39057d6057111a1759ee9f463151639a7bd4d0818`; frozen experiment-tool SHA-256 `a8137f33bc507e3c8a2fa685d75bd99cc89b4512970e602c8dc6e8ba9510b838` |
| RX0 cross-receiver anchor replay | report SHA-256 `1f57f4b58c7e6606917455489a69bc3c97703f1d646e9cf381f307f523aada95`; summary SHA-256 `19d591ec60ef12e0b29fbff0c5bb917fb19082755e510b17fdb9c67dda1392de`; ledger SHA-256 `dffbea6836e66f97281ee74f9380b063eefddafe1432d8d6bde494b03038e832`; manifest SHA-256 `a5422aa6d6a283c3282c04dd9e8c0f21bc63617ac929bc598533f29974da5cdc`; frozen tool SHA-256 `586efda332f1d4ee4329eab5ea95a8ff52e0d4d0e23c3c1b890eaa6bcff53084`; scientific-configuration SHA-256 `c04640173c07dd8c5933c58b84ae3c21b25356e21680f480b3838069682406f2` |

The 150802 analyses share these frozen inputs:

- recording-manifest SHA-256
  `ab55917851a9cd37af94b6145cc719f7b8d9d0809f2202a2dcd1ac38c3e7a31e`;
- RX1 direct-CFO rows SHA-256
  `05f33a0b492b84cda166bc7982c5554778c747f065ed93b4386eda60b3ff582c`;
- causal pre-capture Space-Track 3LE SHA-256
  `9bb59fcf68fa36ce234ae9be79a492f0b92abc23bcf4f040bb5b64b61d3e31ad`,
  collected at `2026-08-25T14:02:12.658586719Z`, `3,952.922 s`
  before the stream-1 first-sample estimate;
- the adjacent earlier TLE SHA-256
  `ac79e846bc149d9bbe4a1847eda5fddc9ca6af9fbe3432d6c58cdc33345ceb8a`,
  whose only changed object, 47657, was outside the visible population;
- RX0 final trajectory-bank SHA-256
  `1c1536cb7336779c1ba028609bd54afef962c5c5890267e69fca5af581e4fd0a`,
  dealiased-bank SHA-256
  `95350c2c6878fabe11fccc03e7017c97cd3beaa9807f581f9c86c52c76026e14`,
  alias-map SHA-256
  `e21104ff1a3dc172d0861a2aa0cb50dd4a59dea296ae380e352d34fb8ab465a8`,
  and strict replay SHA-256
  `4dafe3f8567a8a44d998257d1976253c8fa72fc5da7b73ec1b64061f8265a80b`;
- RX1 final trajectory-bank SHA-256
  `720a3f740c4071de03c3710332dacf6780e904e44d7613135bfd3b3791de1bd2`
  and strict replay SHA-256
  `773a5e131552a0946702daf719da4400b89af6296356aa35146e2c59c2cc6d77`.

The common-orbit artifact states that all named input bytes and executable
sources were read and hashed at startup, parsed from frozen bytes, and rehashed
before output.

## Evidence layer 1: the last-ten audit establishes orbital structure, not a name

The committed last-ten audit used the literal latest ten committed 60-second
recordings: 40 counter-anchored, one-segment, gap-free paths. Its independent
degree-one evidence SHA-256 is
`b929f9189ea4b879aeaa8f661926bea8ec618f01169a62ae4aaede9d2ee4a1ad`,
and its association evidence SHA-256 is
`3b84478aef6f5ea521c5e50bba1e2209ef1fd49120402e6b67f6ce98c5fb2342`.

The population result survives a wider epoch search: 22/26 true-time replica
clusters beat a radio-only line, and both equal-dwell mean and median gains rank
first among 41 matched fields (`p = 1/41 = 0.02439`). That is evidence for
correct-time satellite-like orbital CFO structure. It is not a named-object
result: 17/29 fits reached a `+/-2 s` boundary, only 3/26 clusters had a runner
margin of at least 100 Hz, and the minimum named-cluster FWER was `0.48780`.
The wider-search evidence SHA-256 is
`2ef074c7efd46983dc0ab8005263a016160c11cbed8343711e5cdc8f06294fe4`.

Reconstruction of the full degree-one family found 109 selected tracks, 67
eligible tracks, 21 corrected episode labels, and 15 unique member-set
computations. It produced zero numerical identity-gate passes and minimum named
FWER `0.65854`; its evidence SHA-256 is
`daef7cf79a845d0e89f28d3429935494e4720e0b50bb3c87db1fcac20dbe803b`.
No catalog number recurred across two dwells in 725 persisted model top-five
rows, 150 scalar top-five rows, or the persisted shared/independent dwell
hypotheses.

The strongest causal physical episode selected STARLINK-33874 / 63825 at a
common `+0.35 s` epoch. Its aggregate orbit/polynomial held-out RMS was
`191.74/488.58 Hz`, but one receiver favored its cubic null (`183.15` versus
`144.68 Hz`), the runner margin was `98.55 Hz`, and named FWER was `0.34146`.
The causal cross-RF evidence SHA-256 is
`7ef0c0eef3ea823e9e8dd5c701429bbf9faa847896c85e0363e708fb79cf06a3`.

The adjacent second D6 fragment selected STARLINK-34123 / 63891 with
`162.4/327.6 Hz` orbit/polynomial RMS, but its runner margin was only
`0.031 Hz` and named FWER was `0.65854`. Stitching the first fragment to the
second falsified both names: 63825 missed the holdout fragments by
`100,955.40 Hz` against `99,795.15 Hz` for the polynomial oracle. The stitch
evidence SHA-256 is
`9b01349a0f9674084d47a2120166f24aee705fba902573ca3729884e09056c0d`.
Giving all six fragments separate wrap/reset offsets instead selected a third
object, 67975, at the `+2.5 s` boundary; all fragments lost to polynomial and
aggregate holdout RMS was `3,371.01 Hz`. The six-fragment evidence SHA-256 is
`35ecd05771d745eace5eb108ea5eb55bd1350994538bbf06961295776b358b56`.

The last-ten provenance audit found zero hash mismatches and has SHA-256
`88d90f479fe740b8373994e733c58c0db3e226ef3aff9ae4bd98064b4a24035b`.
Its 40 wrong-time fields are serially correlated controls, so their calibrated
values are matched-field sensitivity results rather than formal exchangeable
permutation probabilities.

## Evidence layer 2: why the RX1-only 59748 fit looks strong

The committed RX1 comparison uses 550 direct GLRT64 CFO observations over
`2026-08-25T15:08:43.165078492Z` through
`2026-08-25T15:08:56.965091292Z`. It searches every one of 561
horizon-visible Starlinks from the causal 10,972-object catalog under

\[
y_i = D_j(t_i + \tau) + b + \epsilon_i,
\]

with only one fitted time shift and one constant frequency offset; it forbids
candidate-specific scale, slope, and curvature.

Under the primary `+/-2 s` search, 59748 has `68.3558 Hz` bidirectional
held-out RMS. The next candidate, 65438, has `445.5211 Hz`, a `6.52x`
separation. The descriptive full-data fit is `55.8907 Hz` RMS at `-0.155 s`
and `-133.022 kHz`. This is genuinely strong conditional candidate evidence.

It is not secure identification even before RX0 is considered:

- the two temporal directions choose incompatible shifts, `-0.345 s` and
  `+0.790 s`;
- fixing `tau = 0` improves combined held-out RMS from `68.3558` to
  `54.4512 Hz`, so the time shift overfits the short, nearly linear arc;
- widening the allowed shift to `+/-30 s` changes the winner to
  STARLINK-30835 / 58219 at about `-22.4` to `-22.6 s`, with
  `55.0544 Hz` held-out RMS, demonstrating catalog/time-shift degeneracy;
- the observer position is a reviewed preset rather than capture-bound GPS,
  antenna boresight is unknown, and the RF frequency is uncalibrated.

In other words, a clean one-receiver curve can rank a candidate decisively
inside a restricted model while still lacking the independent constraints
needed to assign a physical transmitter name.

## Evidence layer 3: corrected RX0 raw-IQ replay

The corrected replay searches RX0 raw IQ near all 15 RX1 primary anchors over
one complete 750 Hz frame period (`3,334` integer epoch hypotheses) and a
`+/-2.5 kHz` CFO neighborhood in 250 Hz steps. It does not copy the RX1 epoch.
Exact Qin and a 17-symbol-rolled control maximize independently over the same
search domain. Three strong first-60% anchors calibrate an RX0-minus-RX1 integer
epoch offset of exactly zero samples; frozen target-binding gates then retain
nine anchors, five in the first 60% and four in the final 40%.

The corrected support accounting is exact and supersedes the earlier wording:

- 135 nominal frame opportunities comprise 126 even-fold
  research-supported rows and nine explicitly incomplete endpoints;
- 117 of those 126 rows pass the stricter, authoritative primary frame-CFO
  contract: 66 in the first-60% calibration fold and 51 in the final-40%
  evaluated conditional fold;
- all nine primary rejections remain in the ledger with reason
  `even_odd_disagreement_above_maximum`.

The 126 research-supported rows therefore must not be described as 126
qualified primary measurements. The authoritative 117-row primary line has
slope `-3,589.8276 Hz/s` and
`25.0578 Hz` residual RMS. A line fit to the 66 calibration rows predicts the
51-row evaluated conditional fold at `27.8737 Hz` RMS. The final 40% is not an
untouched or preserved holdout: Qin evidence from those windows still performs
local alignment and membership selection.

The broader 126-row research companion supplies the receiver-relative frame
registration audit. Every RX0 row has an RX1-supported frame within two
samples: offsets are `-1: 17`, `0: 66`, `+1: 38`, and `+2: 5`, so 66 frame
starts match exactly. On that common frame set, RX0 and RX1 slopes are
`-3,587.933` and `-3,578.230 Hz/s`; the receiver-difference slope is only
`-9.703 Hz/s`. The median RX0-minus-RX1 CFO is `613,784.110 Hz`, and its line
residual RMS is `69.009 Hz`. This is the direct basis for the local same-emitter
claim: both receiver chains recover the same frame timing and nearly the same
Doppler slope after a large nuisance frequency offset.

The precision gain does not add temporal independence. The 117 primary rows
and 126 research rows cluster inside nine 20 ms windows over
`45.475--50.5 s`; the existing RX0 branch already spans `43.6--51.35 s` with
67 observations, `-3,576.124 Hz/s` slope, and `152.082 Hz` residual RMS. The
source capture is counter-authoritative—150,000,000 observed samples equal its
device span, with zero gaps, missing samples, overflows, clipped samples,
constant-IQ refills, or gap-map boundaries—but RX0 and RX1 still share one
Pluto sample-clock/LO domain. The replay is also conditional on the existing
RX0 branch, alias `+2`, local CFO neighborhood, and known Qin symbols. It
therefore strengthens same-emitter tracking, not independent-clock replication
or NORAD identity.

The corrected summary, ledger, and manifest reran byte-identically in a fresh
output directory. At startup and shutdown, the tool pins and rechecks its own
code, scientific configuration, recording manifest, RX0 banks, and RX1 long
evidence/ledger inputs. The RX1 long evidence and compressed frame-ledger
SHA-256 values are
`619a715143c20801efbe8be3dee012b1a83e3fc730d588bb3a2c6cd2382de579`
and `38beb847c417e4b69f8c8ed64acda1d24116ad47531dc2ee3e601d61cd3bda0f`;
the declared and independently decompressed row SHA-256 both equal
`2d40f818bb76723629227704066137c0947a9523742f60fdd1cfad3a79842fd4`.

## Evidence layer 4: the nuisance-rich common-orbit test falsifies identity

The raw RX0/RX1 source interval is `43.6--51.35 s`. After intersecting the
actual observation times, the alias-aware audit restricts both receivers to
their mutual `43.6078--51.2331 s` observation overlap (`7.6253 s`). It uses
250 ms median bins and one shared chronological split: RX1 contributes 310
direct rows in 32 bins (19 train, 13 holdout), while RX0 contributes 67
canonical dealiased rows in 29 bins (16 train, 13 holdout). Equal receiver MSE,
not raw row count, defines the aggregate.

The RX0 branch is the unique strict replay winner at alias `+2`, with 67
observations, 152.082 Hz replay residual RMS, full block coverage, and no
harmful blocks. RX1 is likewise its unique strict replay winner, with 530
observations, 88.680 Hz RMS, full block coverage, and no harmful blocks. These
checks establish admissible branches before the orbit search; the fixed RX0
alias lift is absorbed by its separate intercept and contributes no orbit
specificity.

With separate per-receiver offsets and `+/-200 Hz/s` nuisance drifts, the
training-only common winner is again STARLINK-31640 / 59748. The exact result
is:

| Quantity | Common-orbit result |
|---|---:|
| Candidate count | 242 |
| Candidate / runner | 59748 / 58219 |
| Common epoch | `+2.50 s`, boundary |
| Aggregate train / holdout RMS | `90.415 / 158.151 Hz` |
| Training runner margin | `1.085 Hz` |
| Best alternative held-out RMS | `112.746 Hz` |
| Held-out alternative margin | `-45.405 Hz` |
| Strongest radio-null held-out RMS | `143.143 Hz` |
| Orbit advantage over radio null | `-15.008 Hz` |
| Raw diagnostic matched-field p | `0.04878`, ineligible for identity interpretation |

Neither receiver beats its own held-out linear oracle: RX1 orbit/null RMS is
`86.908/69.487 Hz`, and RX0 is `206.084/190.136 Hz`. The shared-curvature
degree-one null also gives `143.143 Hz`, better than the orbit's `158.151 Hz`.
The training-selected identity loses on holdout to 65438 by `45.405 Hz`.

The catalog number remains 59748 when the allowed per-receiver drift is 0, 25,
or 200 Hz/s, but the epoch flips from the `-2.5 s` boundary at zero drift to the
`+2.5 s` boundary at 25 and 200 Hz/s. Runner margins fall from `66.074` to
`45.017` to `1.085 Hz`. Thus the name is stable only because many locally
similar constellation curves can trade against epoch, receiver offset, and
drift; the fitted geometry is not stable.

The complete numerical identity gate fails: the epoch is not interior; neither
member beats its polynomial; the aggregate fails both the 100 Hz radio-null
advantage and shared-curvature checks; the runner margin is below 100 Hz; a
held-out alternative wins; and the epoch is not stable across drift bounds.
Because these hard gates fail, identity calibration is not applicable. The raw
diagnostic is exactly `2/41 = 0.04878` because one control ties the true field;
it cannot be interpreted as identity specificity.

This is why the dual-receiver result is more skeptical than the single-RX
report. It asks a materially harder question on a shorter common interval and
admits the actual receiver nuisance structure. The added channel confirms the
emitter locally, but the added nuisance degrees of freedom expose that a TLE
curve is not uniquely required: simple radio-only trends and a different
catalog object predict the holdout better. Replicating a signal is not the same
as identifying its spacecraft.

## Consolidated limitations

- RX0 and RX1 are channels of one Pluto. They share a sample clock and are not
  independent instruments; separate offsets and drifts do not remove shared
  front-end systematics.
- The RX0 replay is conditional on an existing trajectory, alias, local CFO
  neighborhood, and known Qin symbols. It is not blind signal discovery.
- Both replay-qualified trajectories were selected over their full spans
  before the retrospective 60/40 common-orbit split. RX1 direct rows are also
  trajectory-conditioned, not independent frame observations.
- The 250 ms bins reduce cadence pseudoreplication but do not establish
  statistical independence.
- The receiver/LNB frequency reference is uncalibrated. Separate offsets absorb
  transmitter, receiver, and LNB error; bounded drift can absorb local shape.
- The observer location is reviewed but not bound into the capture manifest,
  and antenna boresight/gain is unknown. Visibility is geometric, not beam
  authority.
- TLE propagation is causal but conditional on one pre-capture catalog. The
  short arc has no payload identity, calibrated pseudorange, absolute TOA, or
  independent range observable.
- The matched wrong-time fields are correlated controls and calibrate this
  focused post-hoc statistic only. They do not correct across every earlier
  analyzer, grouping, epoch bound, or TLE sensitivity.
- The last-ten corpus has no cross-dwell catalog recurrence and has already been
  exhausted by independent-track, physical-episode, all-track, stitch, and
  wrap-aware falsifiers.

## Required next experiment

Secure identity now requires new information, not another post-hoc search over
the same corpus. The next useful experiment is an explicitly authorized,
predeclared confirmatory RF capture, bounded to at most 30 minutes under the
repository rules. It should:

1. bind measured site coordinates, causal TLE digest, radio serials, applied RF,
   LNB model, and measured frequency/time calibration into every manifest;
2. tune two physically independent radios to the same fixed edge rather than
   treating two channels of one Pluto as independent replication;
3. predeclare one high-elevation pass, collect multiple separated dwells through
   it plus matched off-time controls, and freeze all gates before collection;
4. require the same catalog identity and common interior epoch across radios
   and repeated dwells;
5. require every receiver to beat degree-1/2/3 radio-only nulls, aggregate
   held-out RMS at most 500 Hz, orbit advantage at least 100 Hz, runner and
   held-out-alternative margins at least 100 Hz, and matched-field family-wise
   calibration at most 0.05; and
6. repeat the result on a later pass or at a second station before any production
   identity claim.

No such RF campaign was started. It requires the user's explicit authorization.
