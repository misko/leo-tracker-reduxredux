# Resumed objective and hypothesis register

User-authorized objective: understand the Starlink header/signal structure more
deeply and determine whether recovered bits or stable structures can identify
satellites, using existing DS7/DS8/DS9/DS10, firmware and online literature only.
No new RF. Preserve unrelated changes, scientific fixtures and prior receipts.

The initial goal API creation failed because the prior blocked goal was unfinished.
The user subsequently set the new objective through the app and activated it.
The resumed investigation now has an active app-level goal matching this plan.

## Ranked bounded experiments, fixed before inspecting their outcomes

| Priority | Hypothesis and new discriminator | Evidential value | Feasibility | False-positive risk |
|---|---|---|---|---|
| 1 | A stable early fingerprint predicts candidate identity on a different visit; evaluate independent frame halves and confound-matched different identities | High if transferable | High on cached tracks; labels sparse | High: conditional labels, channel/session confounding |
| 2 | Relative phase within a symbol survives polarity/phase changes better than absolute signs; compare against rank-1 matched design and label permutations | High if it separates identities beyond channel | High | Medium/high: static template and shared channel response |
| 3 | Within-visit early coordinates selected as stable on early RX0 remain stable on later RX1 and another visit, while varying between identities | Direct candidate-bit evidence | High within visits; limited revisit coverage | High: universal constants mistaken for identity |
| 4 | Simple sequence-counter/timing bits follow physical frame indices; fit binary-counter harmonics on early RX0 and test later RX1 with maximum-statistic circular controls | Moderate; cannot identify a field without coding map | High for long cached visits | High: short windows, many coordinates/periods |
| 5 | Known T-state or channel explains apparent identity correlations; stratify state agreement and run metadata-only negative controls | Essential discrimination | High | Medium: incomplete state coverage |
| 6 | Firmware/literature constrain interpreting these outcomes as satellite address versus beam/channel/sequence state | High only with an RF mapping | High for bounded review | High if software offsets mistaken for air offsets |

No renewed blind byte, parity, CRC, convolutional-code or arbitrary alignment
scan: prior tests already failed without an independent mapping constraint.
No identity label inferred from a sign match, and SATAddr is not NORAD identity.

## Design commitments

Use source-hash-bound qualified track caches. First and second reserved evaluation
frames form independent observation halves for each track; never calibrate a
feature using the target frame. Remove pilots and exclude late T-code from early
features. Subtract population means using first-half observations only; report
absolute-axis and phase-invariant features separately. No per-pair alignment
search. Deduplicate visit/RX aliases, exclude same-visit pairs from identity
transfer, and distinguish within-session revisits from different sessions.

Compare same-candidate pairs with different-candidate pairs matched on edge,
channel, rate and receiver; report time, pilot-quality and T-state sensitivity.
Label permutations are conditional exploratory controls, not proof that noisy
orbit associations are true. Stronger-label sensitivity is mandatory. If no
matched examples exist, report coverage failure rather than a negative identity
result. Also report same-edge cross-channel transfer as a separate, explicitly
weaker experiment.

Within-visit tests use chronological discovery/evaluation splits and physical
frame indices, not ordinal positions after quality filtering. RX0 selects and
RX1 evaluates. Report receiver-consensus subsets separately. Freeze masks for
controls. Use familywise maxima for searches over coordinates/periods and account
for multiple feature families; do not report post-hoc winners as confirmation.

All cached evaluation material has been inspected in previous work. New fits can
be held out computationally, but these are exploratory tests, not pristine
prospective confirmation. No bit error rate or field meaning follows from receiver
agreement alone. Numerical outputs stay in ignored local/.

## Coverage-driven amendments and sensitivity tests

The strict first run had three same-candidate pairs and one matched comparison;
no strict cross-session/channel positive pair survived. Before treating this as
a negative finding, add a separately reported mixed-instrument sensitivity:
match receiver/rate pairs instead of requiring equal receivers/rates, and allow
pilot-coherence differences <=0.1 instead of <=0.05. Keep exact channel pairs,
time bins, session relationship and known-state overlap in the matching strata.
Correction now spans eight scope/tier combinations and four feature families.
This amendment was motivated by coverage; it is not prospective confirmation.

Global instrument-stratified label shuffles can break session structure. Require
session+instrument shuffles and a whole-candidate-trajectory name permutation
within sessions, preserving all visit/RX membership of each trajectory. The last
control has little or no power for within-session identity equality and tests
whether cross-session naming contributes beyond episode persistence. Report all
controls rather than selecting the most favorable one.

For a short-term real-sign lead, report descriptive exclusions of symbol 2,
separation cuts at 15/120/7200 seconds, added coarse CFO-difference strata, and
leave-one-candidate-out effects. These are sensitivity checks, not newly selected
confirmatory hypotheses. The 15-second cut is informed by the published fixed
assignment interval; it does not establish GPS-aligned beam boundaries in our data.
