# Gaussian mixture localization on DS9 DS10 and DS11

Follow-up status: the user-authorized 64-recording evaluation is complete, with
22 DS9, 21 DS10 and 21 DS11 scans reset independently to the standard Sacramento
250 km region. Its 192 final attempts passed the provenance/reset audit. Gaussian
sum completed 0/64; greedy completed 12/64, with two sub-kilometre estimates over
all 64 scans. This bounded implementation is not ready for promotion. See the
[64-scan results and visualizations](../reports/2026_09_30_gaussian_sum_64_scan/README.md)
and [interpretation](../reports/2026_09_30_gaussian_sum_64_scan/INTERPRETATION.md).
The earlier first-run history and original plan below remain for provenance.

Status: first gated experiment executed on 2026-09-30 with three concurrent SOL
workers. Prototype and independent checks complete; scientific promotion stopped
when the first DS9 regional replay discarded 13.01% of posterior mass. The broad
stress case also exceeded orbit-time support. All 48 inputs were audited; the
remaining 47 scans were not fitted. See the
[decision report](../reports/2026_09_30_gaussian_sum_single_scan/README.md) and
[frozen first-run protocol](../reports/2026_09_30_gaussian_sum_single_scan/PROTOCOL.md).

Build a small Bayesian estimator that updates several receiver-location
hypotheses as completed RF tracks arrive, while retaining uncertainty about
satellite identity. Prototype the mathematics independently, implement a pure
analyzer, and evaluate independent single recordings from DS9, DS10 and DS11.
Use one coordinator and up to three concurrent `gpt-5.6-sol` workers.

This is a bounded first implementation of the broader
[satellite association and PNT plan](satellite-association-and-pnt.md).

## Scope and success

A single scan means one complete recording with both receivers. Reset location,
association and hardware state for every recording. Tracks within that recording
may update a common posterior; recordings and datasets must not share fitted
position or nuisance states. Fixed model parameters may transfer from development
data only with recorded provenance.

Start with a stationary receiver, regional location mixtures, explicit altitude
uncertainty, one source per coherent track, an unassigned/background alternative,
proper frequency-offset marginalization, and constrained per-RX drift. Preserve
shared errors and observation provenance. Use soft antenna compatibility only
where supported; hard rectangular fields of view and inferred physical LNB roll
are outside this first implementation.

Success means reproducible posterior updates, useful ambiguity handling,
bounded runtime, and honest single-scan evaluation. It does not require forcing
every scan to produce a location or claiming sub-kilometre accuracy. Global
acquisition, moving receivers, free satellite-orbit fitting, raw-IQ extraction
improvements and native acceleration are follow-on work, gated by measured need.

## Data and comparison panel

| Dataset | Frozen authority | Proposed use |
| --- | --- | --- |
| DS9, 105 recordings | [manifest](../reports/2026_09_28_ds9_post_ds8/manifest.json) | Eight development scans selected by chronological zero-based indices `floor(i*(N-1)/7)`, for `i=0..7`, ordered by capture start then session ID. Freeze IDs before fitting. |
| DS10, 187 recordings | [manifest](../reports/2026_09_29_ds10_post_ds9/local/manifest.json) | Reuse the exact eight scans in the [existing single-scan plan](../reports/2026_09_30_ds10_single10/plan.json) for validation. These come from its N24 panel, not directly from all 187 recordings. |
| DS11, 87 recordings | [manifest](../reports/2026_09_30_ds11_post_ds10/local/manifest.json) | Reuse the exact 32 scans in the [existing selection](../reports/2026_09_30_ds11_single10/export-plan.json) for the final frozen-method replay. |

The initial panel therefore contains 48 independent fits per method, not a
48-scan joint estimate. Keep all selected scans, rates, receivers, failures and
timeouts; never replace a difficult scan. Expand beyond this panel only after
the coordinator records what scientific question the additional scans resolve.

These datasets and site coordinates have already been explored. DS9 development,
DS10 validation and DS11 final replay are operational roles, not claims of
untouched holdout data or independent-site validation. The
[pose audit](../reports/2026_09_30_rx_sky_coverage/README.md) subsequently verified
capture-bound installation evidence for all three datasets; the reference remains
operator-supplied, with unknown survey accuracy, altitude and RF phase centers.

## Coordinator preparation and shared interface

Before dispatching workers, freeze the following small research interface and
give each worker an owned output area. Keep it private to the experiment until
the numerical and real-data gates pass; do not change published contracts.

- `ScanEvidence`: source digests, RX and hardware epochs, absolute timestamps,
  physical observation IDs/support intervals, frequency samples or qualified
  sufficient statistics, covariance, alias alternatives and discontinuities.
- `OrbitProvider`: archived ephemerides, frame/time/frequency conventions,
  provenance, coverage and declared orbit-error model. Catalogue selection must
  cover the supported geographic region without consulting measured fit scores.
- `FilterConfig`: location/height/time priors, nuisance and background priors,
  candidate policy, mixture budget, pruning policy, seeds and resource limits.
- `PosteriorSnapshot`: weighted location modes with conditional nuisance states
  and identity history, predictive evidence, association/background probabilities,
  discarded mass, boundary/observability flags, support consumed and status.
- `RunReceipt`: exact inputs, code/dependency/config identities, command, resource
  accounting, terminal status and prediction digest. A separate evaluator adds
  reference-distance results after predictions are sealed.

The verifier/evaluator may read pose coordinates. Inference receives explicit
priors without pose truth or reference-scored candidate labels. This is interface
separation in a shared workspace, not a security boundary. Priors must have named
provenance and must not be centred on a revealed answer or a pooled fit.

## Concurrent SOL work packages

| Worker | Prototype responsibility | Implementation ownership | Required handoff |
| --- | --- | --- | --- |
| SOL A, evidence and replay | Audit selected scans, bindings, support overlap, available pre-association tracks, covariance and causal TLE coverage. | New read-only export/replay tools and adapter-owned tests; no filter mathematics. | Frozen evidence bundles, extraction limitations, source inventory and deterministic replay command. |
| SOL B, inference | Write the likelihood/update specification and a minimal Gaussian-sum prototype with background and nuisance marginalization. | New pure analysis module and component tests; no storage or evaluator imports. | Filter API, equations, synthetic demonstrations, bounded split/merge/prune policy and state-lineage diagnostics. |
| SOL C, independent verification | Build exact small-mixture and geographic-grid numerical oracles against the shared interface. | Independent tests, evaluator, matched baselines and plotting; do not reuse B's update algebra as the oracle. | Numerical audit, failure injections, reference-isolation tests and comparison report generator. |

The coordinator owns shared interface changes, integration, frozen protocols,
scientific decisions and compute leases. Workers use disjoint paths and propose
cross-owned edits through the coordinator. Do not let workers spawn more agents.
If isolated worktrees are needed, inspect task attachments first and reuse suitable
active worktrees. Preserve all unrelated work in the current checkout.

## Execution waves and gates

| Wave | Concurrent work | Gate before advancing |
| --- | --- | --- |
| 0, preparation | Coordinator freezes interfaces, scan selection, source revision and budgets. | Exact dataset IDs and prior provenance; selected artifacts available or explicitly blocked. |
| 1, prototype | A audits/exports a DS9 smoke scan; B builds the mathematical prototype; C builds synthetic oracles using the frozen interface. | Evidence can load without truth; prototype matches exact calculations and preserves ambiguity. |
| 2, implementation | A implements chronological replay; B implements the bounded filter; C runs independent numerical and adversarial tests. | Integrated synthetic suite and one DS9 scan complete with full receipts; no unexplained pruning, duplicate evidence or covariance defects. |
| 3, development and validation | A runs the remaining DS9 panel; B profiles and performs predeclared synthetic/budget checks; C audits results. After a DS9 config freeze, A runs DS10 while B/C check reproducibility and robustness. | Choose and freeze one main configuration, its baselines, thresholds and all DS11 analysis rules. Record every DS10-driven revision. |
| 4, final replay | A runs DS11 batches; B performs only predeclared robustness checks under frozen settings; C independently evaluates and generates figures. | Account for every planned attempt, preserve failures, and publish an advance/repair/stop decision. No DS11-driven scientific retuning in this round. |

Three agents may develop concurrently; expensive numerical jobs have a separate
two-process limit. Dataset workers may verify or summarize while waiting for a
compute lease. Parallelize tasks with independent inputs rather than evaluating
DS11 while the model is still changing on DS9 or DS10.

## Prototype mathematics and required tests

Maintain the joint distribution of location, satellite-history alternatives and
the hardware states that affect future tracks. For each new track, branch each
parent over plausible satellite identities and background, evaluate predictive
evidence, update conditional continuous states, then normalize globally.
Marginalize track-local linear Gaussian offsets analytically. Carry persistent
RX drift and shared satellite uncertainty across the measurements they affect.

Candidate priors depend on location and detection opportunity. Evaluate that
variation across a broad component, or split it before applying local Gaussian
updates. Sum whole-track satellite likelihoods; do not switch satellites freely
between samples. Use full normalized densities, including covariance terms,
with identical observations under signal and background alternatives.

Before real-data expansion, C must demonstrate:

1. Linear Gaussian recovery and exact small-mixture weights, means and
   covariances; sequential/batch agreement where the model makes it applicable.
2. Agreement with a sufficiently resolved regional grid, including genuinely
   separated modes; quantify grid and mixture approximation error separately.
3. Correct background behavior for outliers and absent true satellites, with
   stable normalization for extreme log likelihoods and rejected candidates.
4. Duplicate-observation rejection, proper shared-error covariance, and no
   artificial evidence gain from aliases, replicated candidates or both RXs.
5. Recovery from wrong early identity preference when later evidence supports
   another retained mode; explicit failure when the true region is unsupported.
6. Finite positive covariance, sensible low-information behavior, deterministic
   replay, bounded memory/work, and visible discarded mass and boundary status.
7. Poison tests proving changes to evaluator-only coordinates cannot change
   inference, and changes to future measurements cannot change a causal prefix.

Declare numerical tolerances and Monte Carlo coverage targets after the synthetic
pilot and freeze them before DS10/DS11 scoring. Test genuine correlated nuisance
models; merely inflating independent per-track noise is not equivalent.

## Real data experiment

A must establish that exported tracks and candidate banks are suitable for this
experiment. The sky audit found archived associations conditioned on an old
site and only a small selected subset of eligible candidate groups. Reusing their
winning NORAD labels or narrow shortlist would bias a broad-location test. Reuse
source-bound pre-association measurements and build a response-free candidate
universe over the declared prior region. Stop an unsupported comparison rather
than silently inheriting truth-directed or region-incomplete candidates.

Reuse available derived products through public readers. Check covariance quality,
frequency sign and RF conversion, TLE age/time causality, aliases, discontinuities
and source overlap explicitly. If uncertainty must be estimated, fit its rule on
development data and freeze it. No raw-IQ reprocessing is part of this first plan.

Use three primary arms on identical evidence and priors: the Gaussian-sum filter,
a greedy one-branch filter with the same physical likelihood, and the unchanged
prior without RF updates. Keep the existing independent Student-t and fast
shared-scale results as historical context; treat them as matched comparisons
only when inputs, priors, search support and scoring opportunities really match.

Start with one regional prior and one declared broad/multimodal stress prior.
Choose their centers/scales/weights without reference-error optimization. Limit
the stress prior to a region the orbit bank and grid oracle actually support.
Run the stress case first on synthetic data and the DS9 panel; freeze a small
deterministic real-data subset for later robustness checks. Avoid a full sweep
over nuisance priors, mixture caps and geographic starts.

Replay non-overlapping completed tracks chronologically, with stable tie handling
and a shared factor for dependent simultaneous observations. Score the next
evidence block before assimilation. Completed-track retrospective products are
not automatically causal online detections: audit extraction support, and label
the result completed-track replay unless all prefix features were available then.
Predeclare a within-scan future-support test; refit any feature summaries using
only prefix data before claiming future prediction.

## Metrics and figures

Report each dataset separately and every attempted scan: terminal status,
abstention, reference distance for a predeclared highest-mass-mode point estimate,
median/p90/worst error, sub-km fraction over all attempts, error relative to the
prior-only control, predictive log score, background/association entropy,
posterior region area, runtime and peak memory. Compare full posterior predictions
in a common observation space; do not compare incompatible native score scales.

Use simulated known truth for coverage and identity-accuracy claims. On real
scans, report reference containment as a descriptive diagnostic: the roof point
is unsurveyed, repeats one site, and does not establish satellite identity truth.
Do not interpret 48 fits as independent experiments in different environments.

Generate location-density maps at fixed consumed-support checkpoints, candidate
and background probability timelines, paired per-scan errors against controls,
error-versus-support curves, calibration figures on simulations, and runtime
versus mixture size. Distinguish a small confident wrong mode from an honest
multimodal or abstaining result.

## Budgets and deliverables

Proposed initial limits: at most three SOL workers, two numerical processes with
one numerical thread each, one bulk archive reader, 180 seconds per export and
90 seconds per scan/arm including load. Use the existing installed interpreter;
the previous benchmark recorded UV startup delays under filesystem load.
Set an enforceable memory limit after inventory and before launch.

Limit a real-data batch to eight scans and 15 minutes elapsed, including its
prerequisites. Stop at the first limit, preserve completed results and timeout
receipts, and mark unstarted work as pending. Review each batch before the next;
do not schedule a multi-hour unattended campaign or expand limits after seeing
scientific outcomes. Engineering retries preserve original receipts and inputs.
QNAP and all frozen authorities stay read-only; no RF collection is included.

Deliver a pure tested analyzer, independent oracle tests, read-only adapter/replay
tools, frozen configuration and scan inventory, reproducible commands, prediction
and evaluation receipts, figures, and one decision report. Promote only after
correctness and resource gates pass and the chosen scientific tradeoff is supported
on the frozen replay. A correct estimator that adds no useful single-scan location
information is a valid stop result, with the limiting evidence identified.

Each worker launch should name its role, owned paths, exact inputs/interface
version, gate, resource lease and output root. Require a handoff containing code
changes, tests, commands, artifact digests, unresolved assumptions and terminal
status. The coordinator integrates those concrete artifacts before closing a wave.
