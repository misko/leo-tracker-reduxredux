# CH8 correction investigation, round 1

Objective: develop and evaluate a generalizable CH8 measurement correction that improves full-channel localization. Investigate continuous CFO refinement, pilot-response mismatch, and receiver-frequency calibration in parallel, using existing recordings, causal TLEs, standard regional initialization, and GPS only for final evaluation. Deliver a reproducible comparison and either a validated improvement or an evidence-supported next step.

The preceding goal turn proposed the work without executing it (no progress under the goal accounting rule). This round starts actual implementation and experiments. Two SOL agents own CFO and pilot-response branches; the agent service rejected a third thread, so root owns calibration, integration, review and publication. No runtime components or published contracts are changed in this experimental stage.

## Fixed development cohort and interpretation

- Use the first two chronological usable original DS24 fast cases, DS24-0010 and DS24-0011. These are exposed development cases, not independent validation. No case is selected by position error.
- Full reference: `/srv/bulk/leo/research/ds25-20261024/family_cavity/position/DS24-XXXX.json`. Regional box is 25 by 25 km centered at 37.906, -122.545; position parameter origin is that center. Candidate banks and causal history remain original. No following TLE or GPS enters inference.
- Same original observations, IDs, aliases, candidates, other priors, and budgets in each c=0/fitted-c pair. A measurement comparison retains the same original likelihood membership. Detection recovery is a separate experiment and must not disguise a changed denominator.
- A 10% median full-channel position-error reduction with no mean/P95/availability regression is the desired broader evaluation target, not a guaranteed outcome or a meaningful promotion rule on two cases.
- Saved-identity cold regional-center refits are controlled mechanism tests, not full regional association-search reruns. A qualifying candidate must be evaluated through the regional pipeline before claiming operational improvement.
- Current DS24/later baselines have prior exposure. A future validation claim must audit exposure and freeze an unexamined correction panel before evaluating it; do not relabel exposed scans as held-out generalization.

## Branches

1. CFO: longest eligible complete curved owner per RX and CH7/8 in each case; every original owner ID must belong to both c arms. Tie-break span, points, key. Freeze before correction; verify historical both-RX detector parity on fixed 1/3 and 2/3 time quantiles, then process complete owners if qualified. Existing continuous within-winning-cell GLRT64 estimator, unchanged admission and rank. Full panel <=1200 native points, no truncation/replacement to satisfy the cap. See `cfo/PROTOCOL.md` and its sealed nomination.
2. Pilot: one passed and one near-gate-failed target per case/RX/CH7/8, nearest scan midpoint then visit, original max-margin rank. Sixteen target slots, paired physical windows deduplicated. Compare existing flat response and per-tone complex response with held-symbol prediction and wrong-sequence/noise controls; received-clock diagnostic only as separately identified test. See `pilot/panel.json` and branch protocol. Full-window acquisition exposure remains explicit.
3. Calibration: compare existing RF-scaled RX smooth design against the same-width native-Hz RX smooth design, without extra terms. Train on original retained CH1-7 curved and predictive data, then evaluate original retained CH8 curved data. Zero phase references and regional-center position start, five refresh rounds and 48 position steps per round. Existing aliases, labels, support, powers and priors are fixed, so this is conditional channel prediction, not blind identity validation. CH8 point-noise proxies can use original RF-only polynomial noise; no CH8 posterior noise precision is transferred. Preserve full joint nuisance covariance in held prediction. Nominal Gaussian approximation for unseen Gamma noise uses E[1/tau]=2.

For calibration, advancement requires lower held-CH8 negative twice log predictive density in both cases and both c arms, aggregate improvement at least 10, no increase in aggregate raw held-CH8 RMS, and converged training phase/precision checks. This is a fixed development screen, not a calibrated hypothesis test. Rejecting a branch does not establish the physical model is false. No geographic result will choose this screen.

## Execution and artifacts

Use existing bounded readers only. QNAP stays read-only; no new RF and no raw IQ in publication. Limit numerical jobs to ten minutes with live handles and receipts; retain missing/failed slots. Each branch owns its directory, uses apply_patch for handwritten changes, and tests new numerical behavior. Root verifies source/input hashes, accounting, c pairing and figures before publication to remote main under the standing user instruction.

Frequency fit, trustworthy association, and position accuracy are distinct outputs. A result satisfying only one does not imply the other two. All failures, unchanged operational fallbacks, and scope limitations remain in the report. Completion requires actual experiments and the full comparison, not this protocol.
