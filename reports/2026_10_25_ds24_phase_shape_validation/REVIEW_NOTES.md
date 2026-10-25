# Prior evidence: established findings and open mechanisms

This note uses already published findings, before opening the current later-panel
outcomes. The comparator remains fresh ALGO02-v1 plus qualified causal signed
phase priors and equal-assignment-prior family cavity. No additional ALGO release
or operational change follows from these diagnostics.

| Question | What the existing experiments establish | What remains open |
| --- | --- | --- |
| Does more association coverage improve position proportionally? | DS23 graph-to-native accepted coverage rises70.71→74.41%, while fitted-c mean changes1.434→1.426km and P95 worsens. Grouped new-family prediction helps the full410 mean but worsens the fast204 mean/median. | Missing evidence can still matter, particularly for outliers. Point count is not independent geometric information; postfit accepted IDs must stay distinct from position-likelihood membership. |
| Is receiver error irrelevant? | The shared RX1-rf50 candidate improves the24-case fitted-c mean1.220→1.120km, with11 improvements,7 regressions and6 fallbacks. A direct held-family cross-RX contrast improves projected RMS only88.996→88.411Hz. | The contrast supports some relative structure under its fixed labels/noise model, but its absolute position influence and physical origin are not identified. Same-family differences also retain source/path effects and cancel useful common Doppler. |
| Can a held-frequency score reliably choose receiver-driven movement? | Fresh family partitions retain only3 corrected movements; only1 improves geographic error. Previously favorable example sign separation does not reproduce. | A later frozen-cohort comparison is needed. Existing family holdouts still inherit RF-dependent labels/noise/selection and are not unseen-recording validation. |
| Is orbital timing/shape a stronger ambiguity? | Local median weak-axis scale is534m; treating timing as known gives110m, receiver coefficients known386m, timing+shape known56m. The largest phase/weak-position correlation has median0.935. | These are local unavailable-information controls, not calibrated confidence or achieved errors. They do not prove an actual orbit error in a particular scan. |
| What did synthetic component removal add? | With inference priors unchanged, removing generating timing+shape deviations changes fitted-c mean0.468903→0.296559km, improving6 and worsening2 of8 realizations. Removing generating receiver deviations gives0.474285km. | Joint removal does not distinguish timing from shape or identify their interaction. Labels, selection, powers and the conditional generating law remain fixed; this is not end-to-end calibration or an instruction to narrow real priors. |
| Are the fits merely trapped at different continuous minima? | Thirty targeted full-channel restarts agree within2.06cm for the tested assignments; transferred half-channel labels do not yield a qualified better full-data solution. | Discrete identity alternatives and model bias remain. This is evidence against generic extra starts, not proof of the globally correct identity/model. |
| Would higher sample rate or feed angle supply precision directly? | All24 usable DS24 fast scans use10MSps. Cleaner RX2 remeasurement reduces scatter without a qualified cohort mean/median gain. Bands share a median11 calibration families; their weak axes differ only17.7degrees. | No controlled sample-rate effect has been identified. The nominal40-degree feed angle changes visibility, not measured bearing or a separated spatial baseline. New geometry must be demonstrated while accounting for shared uncertainty. |

Sources: [DS23 recovery review](https://github.com/misko/leo-tracker-reduxredux/blob/5217788f231f9edce40ddca515a636a26bb97659/reports/2026_10_23_ds23_opportunity_review/README.md),
[grouped new-family experiment](https://github.com/misko/leo-tracker-reduxredux/blob/5217788f231f9edce40ddca515a636a26bb97659/reports/2026_10_22_ds23_dbg01_iteration_007/README.md),
[receiver/orbit controls](https://github.com/misko/leo-tracker-reduxredux/blob/5217788f231f9edce40ddca515a636a26bb97659/reports/2026_10_24_ds24_receiver_orbit_controls/README.md),
[movement replication](https://github.com/misko/leo-tracker-reduxredux/blob/5217788f231f9edce40ddca515a636a26bb97659/reports/2026_10_25_ds24_movement_policy/README.md),
[bottleneck evidence](https://github.com/misko/leo-tracker-reduxredux/blob/5217788f231f9edce40ddca515a636a26bb97659/reports/2026_10_24_ds24_bottlenecks/README.md),
and [component/identity controls](https://github.com/misko/leo-tracker-reduxredux/blob/5217788f231f9edce40ddca515a636a26bb97659/reports/2026_10_25_ds24_identity_components/README.md).

Identity uncertainty is concrete rather than a generic caveat. A symmetric
eight-candidate causal challenge finds0011's58175/63312 pair separated by only
0.384/1.289 objective units, and0012's57743/66259 ranking reverses across saved
parent states. The states differ in position and calibration, so that reversal
does not isolate c. On0013,60108 predicts three additional whole owners better
than the examined alternatives, but all owners use RX1 and were originally
selected from graph rows already assigned60108. Neither a broad normalized
polynomial null nor conditional shortlist weights provide calibrated identity
probabilities. Strong evidence against one null does not resolve a near-tied
satellite pair. The [published identity findings](https://github.com/misko/leo-tracker-reduxredux/blob/5217788f231f9edce40ddca515a636a26bb97659/reports/2026_10_25_ds24_identity_components/identity/FINDINGS.md)
retain those selection and shared-receiver limits.

Residual qualification is also separate from accuracy. Known-label noisy fast
simulations pass gates with errors reaching1.09km, whereas noiseless0.8–2.5m
fits fail normalized ACF. The real residual audit finds only2 ACF-only records
among296 current unowned curve/arm records, at22.63/40.38Hz rather than the
millihertz deterministic edge. These facts justify neither blanket gate waivers
nor treating gate passage as an accuracy certificate.
[Fast controls](https://github.com/misko/leo-tracker-reduxredux/blob/5217788f231f9edce40ddca515a636a26bb97659/reports/2026_10_25_ds24_fast_identifiability/README.md),
[real ACF audit](https://github.com/misko/leo-tracker-reduxredux/blob/5217788f231f9edce40ddca515a636a26bb97659/reports/2026_10_25_ds24_next_directions_review/acf/FINDINGS.md).

A generic nonlinear-phase or importance rewrite would repeat substantial work.
The existing five-case conditional parent-phase audit uses829,440 draw-evaluations
and predicts at most22.795m local shift, with0.062m independent-seed disagreement.
Gamma evidence and Gaussian-volume checks also exist. They do not integrate the
full joint nonlinear phase/precision/shape-design/position posterior; a new test
must identify an omitted coupling and qualify numerics under the same prior law.
The R2 direct integral concerns only a new target's explicitly conditioned phase
law. [Method inventory and exact audit receipts](https://github.com/misko/leo-tracker-reduxredux/blob/5217788f231f9edce40ddca515a636a26bb97659/reports/2026_10_25_ds24_next_directions_review/methods/FINDINGS.md).

The present iteration is discriminating because it separates phase from shape
in the same saved generating draws and tests a frozen receiver candidate on an
exact later panel. Those outcomes must be assessed after independent scientific
sealing. They should not trigger another tuned selector on the same examples.
Future recovery should qualify identity and additional geometry/time support,
preserve old accepted IDs, and retain an unresolved outcome. Match c arms and
report frequency fit, coverage, position distribution, failures and runtime
separately. Same-site testing and the scoped exposure ledger do not establish
new-location transfer or proof that no outside geographic inspection occurred.
