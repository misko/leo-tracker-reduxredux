**Identity-support replay: limited numerical closure and a new RX2 evidence lead**

The bounded replay finishes **17/24 arm comparisons** and proves finite-pool
model ordering for **15/24**. None meets the new absolute-score precision
criterion; seven comparisons lack a complete result. These are distinct
outcomes, not an accuracy improvement or operational identity qualification.
The separate metadata/geometry branch identifies three unused curved RX2
sources, **124 distinct native IDs**, with full nominal phase visibility for
60108. Their CFO has not been compared with that hypothesis. The reference
algorithm is unchanged; no position fits or fresh simulation draws occur.

This iteration follows the
[completed evidence review](https://github.com/misko/leo-tracker-reduxredux/blob/82bc36cbd138b7024bd7af4f988032f1da5255cd/reports/2026_10_25_ds24_review_next_actions/README.md).
It answers the bounded numerical and witness questions, with the broader
precision assessment and stopping rules in [REVIEW_DECISIONS.md](REVIEW_DECISIONS.md).

**The same twelve regression observations, with a declared support-law change**

The replay reuses the prior two layouts' eight physical and four polynomial-null
observations, their ordinary eight-candidate shortlists, both c arms and exact
saved conditional backgrounds. No parent is relearned and no true candidate is
forced, rerolled or backfilled. These are existing regression fixtures; the old
full-parent generator versus shortlist-cavity scorer mismatch remains. This is
not a fresh matching-law simulation or a calibrated identity test.

The new physical event requires nominal line of sight at every retained native
timestamp. Invisible phases contribute zero under the unchanged Student prior
normalization on [-15,+15] s. This is an explicit visibility/event-model change,
not merely an arithmetic repair or a visible-mass-conditioned prior. It does
not marginalize visibility over Gaussian physical modes or model GLRT detection.
The original physical modes, finite aliases, covariance, source constants and
density normalizations remain.

Piecewise visibility certificates use the original linear bank interpolation
and Earth-rotation convention. Positive quadratic algebra and log-domain
integration avoid cancellation/underflow. An analytic precheck demonstrates
that two quadratures can both miss an off-grid narrow mode, so agreement alone
cannot certify precision. The frozen method therefore also bounds physical
evidence between interpolation panels using derivative envelopes and includes
uncertain horizon-root mass. Bounded refinement may stop with nonqualification.

Two results are reported separately. **Absolute precision** requires the
reported objective within 0.001 of both ends of its full-support enclosure,
plus required independent comparisons. **Ordering** can be proved with much
wider individual intervals when one model's lower evidence exceeds every
competitor's upper evidence, including all eight physical candidates and the
proper polynomial null. Unknown bounds block that proof.

| Arm / generating condition | Selected | Complete | Ordering proved | New absolute precision |
| --- | ---: | ---: | ---: | ---: |
| c0 / physical | 8 | 7 | 6 | 0 |
| Fitted c / physical | 8 | 6 | 5 | 0 |
| c0 / polynomial null | 4 | 2 | 2 | 0 |
| Fitted c / polynomial null | 4 | 2 | 2 | 0 |
| Total arm comparisons | 24 | 17 | 15 | 0 |

All 15 proved finite-pool winners agree with their existing generating label or
kind: 11 physical and four null arm results. The 13 completed physical arms
also raw-rank truth first. Two completed physical comparisons fail the strict
null-reference arithmetic guard: Cholesky/eigensolve objectives differ by
4.78e-7/4.91e-7 against the frozen 1e-7 limit. Seven comparisons are unavailable
at the execution deadline. All 192 predeclared candidate contexts remain in the
tables: 136 have complete arm results, four additional partial checkpoints are
preserved, and the remainder is explicitly unavailable. No failed winner is
replaced by another model.

![Distinct old quadrature guard, new absolute precision and ordering outcomes](scientific/report03/precision_vs_order.png)

The old seven-of-eight physical results per arm were **quadrature guards under
the old visibility rule**, not the new complete-evidence precision certificate.
The old null guards passed zero of four per arm. Their counts are retained for
provenance, but they are not comparable performance rates: the event law and
requirements differ. Zero new absolute-precision qualifications does not prove
the primary objective values wrong; their required precision is unestablished.
The large-gap ordering certificates do not resolve the real close competitors
or validate an identity threshold.

![Raw score gaps remain diagnostic, including unqualified outcomes](scientific/report03/raw_model_gaps.png)

Science uses 477.013 cumulative worker-seconds and 299.839 s wall time under the
600-worker-second cap, two workers and one BLAS thread each. The conservative
wall deadline is not extended when one worker finishes. There is no rescue,
scientific retry, fresh draw, position fit or accuracy evaluation. The branch
stops here; another extreme-score numerical campaign is not justified by this
enabling result.

Sources: [frozen protocol](scientific/PROTOCOL.md),
[complete outcomes](scientific/report03/outcomes.csv),
[all candidate contexts](scientific/report03/candidate_details.csv),
[summary](scientific/report03/summary.json),
[RF seal](scientific/RF_seal.json) and [authoritative terminal audit](audit/terminal02.json).
The separately versioned final figures use the accurate “old quadrature guard”
label. Earlier reporting artifacts and the first audit failure are preserved;
no scientific score or decision is changed by those presentation repairs.

**Two different witness-availability questions**

Selection is frozen from receiver, complete native-ID ownership, curvature,
time and RF metadata before any target CFO comparison. The canonical inventory
contains 146 complete owners, including 65 RX2 owners and 38 curved RX2 owners.
Both arms' full 3,784-ID original accepted ledgers, including postfit extensions,
remain intact. No partially used owner is trimmed into a new witness.

| Metadata question | Result |
| --- | ---: |
| Unused curved RX2 with overlapping/adjacent reference support | 0 |
| Time-supported noncurved predictive-only RX2 candidates | 2 |
| Time-supported same-carrier eligible sources | 0 |
| Separate whole-scan unused curved RX2 pool | 3 sources / 124 IDs |

Thirty-five of 38 curved RX2 owners touch old accepted IDs; 27 lack the original
time support. These counts overlap. The two time-supported noncurved sources
have 10/9 distinct IDs on another carrier; they remain predictive-only metadata
candidates and never calibrate receiver offsets/drifts. Their presence does
not satisfy the curved prerequisite or trigger an RF test.

Temporal overlap is relevant to simultaneous receiver calibration, but an orbit
can predict a later source across a gap. The coordinator therefore separately
froze a whole-scan question that drops **only** the time restriction. It retains
every eligible source, without using candidate/alias columns or CFO closeness:

| Complete RX2 source | Native IDs | Time interval, s | RF center, GHz |
| --- | ---: | ---: | ---: |
| CH3/T002 | 24 | 220.492868–242.819219 | 11.4403125 |
| CH5/T001 | 57 | 235.467098–293.937196 | 11.9403125 |
| CH4/T000 | 43 | 236.130545–264.829165 | 11.6903125 |

CH4 matches the historical RX1/CH4 carrier, without overlapping its time support.
Equal carriers do not by themselves establish the same transmitter path or
constant. All 124 IDs are mutually distinct and unused by both original accepted
ledgers and the historical 189 RX1 IDs.

The fixed 60108 geometry check certifies full nominal phase support [-15,+15] s
for every retained timestamp of all three sources: 3,844 interpolation pieces,
no unresolved interval or horizon-root bracket. It uses only the hash-bound
causal nominal bank and saved c0 RF position, with no bank extrapolation,
evaluation coordinate, measured CFO, score or fit. Runtime is 0.215 s under a
30 s single-thread cap. This is hypothesis feasibility, not true-orbit visibility,
physical-mode visibility calibration or proof that any source is 60108.

![All RX2 intervals, preserving time-supported and whole-scan distinctions](witness/availability02.png)

Graph extraction itself was response-selected, and the four historical RX1
owners were found under a label. Their 53+85+36+15 point comparisons are not
repeated. This further metadata selection is independent of a new target-label
score; it is not an RF-blind corpus sample. All exclusions, original ledgers,
source hashes and schema/environment false starts remain saved.

Sources: [time-supported inventory](witness/FINDINGS.md),
[separate whole-scan question](witness/WHOLE_SCAN_FINDINGS.md),
[exact whole-scan pool](witness/whole_scan_inventory.json),
[geometry findings](witness/GEOMETRY_FINDINGS.md),
[geometry seal](witness/geometry_seal.json) and
[illustration seal](witness/availability02_seal.json).

The concrete next real-data question is ordinary full causal catalogue
nomination for **each** of the three sources, with no forced 60108, best-source
selection or assumption that all three share one identity. A separately frozen
predictive test must retain null/unresolved outcomes, shared discovery/radio/orbit
covariance, appropriate source constants and matched c0/fitted-c data and budgets.
Do not sum overlapping-discovery comparisons as independent evidence. This
iteration runs no such RF test or association. Active-parent phase-dependent
mode treatment remains a different possible approximation check; repeating
target/identity B(phi) integration or old RX1 owner scores would repeat work.

No operational behavior changes. The existing cohorts are exposed development
evidence. A broader frozen comparison and an exposure-checked unused validation
block are prerequisites for a new ALGO claim. [Replay and artifact limits](REPLAY.md)
describe the exact new files and external historical dependencies.
