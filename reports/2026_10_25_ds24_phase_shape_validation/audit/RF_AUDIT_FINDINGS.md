# Independent RF and saved-evaluation review

The frozen later-recording experiment supports an ability to absorb shared RX1 frequency residuals. It does not establish a useful general localization correction. Retain the existing reference and do not promote `fast_rx1_rf50` from this panel.

The final [RF seal](../validation/RF_seal02.json) passes all four required flags, with all eight selected cases terminal and all eight original baseline pairs available and qualified. Independent replay covers 48 saved endpoints, their original residual/phase decisions, physical-factor contracts, native likelihood ownership, and postfit ID accounting. The authoritative seal records 29.79324368480593 s cumulative audit time under its 180 s cap. No audit optimization or geographic read preceded this seal.

The [first audit](validation_terminal_audit.json) and [failed seal](../validation/RF_seal.json) are preserved. That audit stopped on the legacy curved-only 0001 summary's missing top-level final phase-change field. The separately frozen [repair](validation_terminal_repair01_freeze.json) reads the existing final value from the exact five-epoch history in audit-local copies: 6.62634101644688e-5 s / 4.737664391546437e-5 s. It rejects incomplete/nonfinite/conflicting history. Three repair tests pass. No saved scientific output, fit, rule or adoption decision changed. Hash-verified carryforward of 42 successful replays plus six new replays gives the final 48; both receipts are retained.

Six candidate pairs pass the original gates. Cases 0003 and 0008 fail and retain the exact fresh baseline in both c arms. The former fails the curved-source slope check on RX1 CH7 T004 (27 IDs, assigned 52288; c=0 conditional slope z=3.238); the latter fails the saved predictive-source compatibility check on RX1 CH3 T003 (31 IDs, assigned 62897). The saved 0008 summary does not identify a more specific numeric subpredicate. These are inherited assignments, not independently validated identities. Phase convergence alone would not qualify either failed pair.

Every branch uses the same native position-likelihood membership: 24,122 distinct IDs from 33,859 native GLRT points. The primary policy preserves all baseline postfit accepted IDs. The two rejected raw candidates lose 27 and 31 such IDs per arm; these losses remain diagnostic, rather than becoming a new adoption rule. Increased postfit compatibility does not increase the position likelihood used in this comparison.

After root authorized the frozen evaluator, an independent [saved-table readback](evaluation_readback.json) verified the report hashes, all 64 rows, exact eight-case denominator, frozen fallback decisions, unchanged likelihood ownership, summary statistics and outcome counts. The [CSV](../validation/report/positions.csv) gives:

| Arm | Reference mean → policy mean, km | Reference P95 → policy P95, km | Reference max → policy max, km |
| --- | ---: | ---: | ---: |
| c=0 | 1.242579 → 1.239835 | 2.830039 → 2.998630 | 3.415129 → 3.720985 |
| fitted c | 1.239054 → 1.223610 | 2.829220 → 2.955866 | 3.405038 → 3.665544 |

Each arm has three improvements, three regressions and two exact fallbacks. The matched cold baseline equals the fresh reference in position, RMS and objective for every case and both arms. Thus the added RX1 basis, rather than the tested restart/budget difference, produces the changed results.

Primary-policy mean curved RMS decreases by 3.668304 / 3.661708 Hz and mean negative-twice-ELBO by 92.888579 / 93.012114 in c=0 / fitted c. Position improves by only 2.745 / 15.444 m on average, while both descriptive tails worsen. In 0007 the fitted-c RMS improves 5.916773 Hz but position worsens 260.506 m. All-eight raw candidate averages include two unqualified pairs and remain diagnostic. Better fit is therefore insufficient evidence of a beneficial position correction.

The highest-value next identity experiment is complete-nomination falsification, as specified in the [design note](IDENTITY_FALSIFICATION_DESIGN.md): generate a source under the same declared uncertainty law, run ordinary causal catalogue nomination without forcing the true label into the shortlist, preserve misses and an unresolved outcome, and test genuinely held whole-source evidence with shared nuisance covariance. This can distinguish incorrect identity/selection from inference conditional on a supplied identity. Repeating a handpicked wrong-label comparison would not close that gap.

The synthetic factorial independently supports sensitivity to both generating timing and the full three-mode shape block; it does not identify a deployable prior change. Its nonzero observation interaction includes the phase-dependent shape design before estimation. A subsequent approximation test must isolate that specific coupling under the same prior law, rather than add generic flexibility or narrow priors using GPS. See [synthetic audit findings](FINDINGS.md).

The integrated root README has no material numerical or interpretation discrepancy in this review. Eight later same-deployment recordings, under an established-site assumption without a capture-bound site ID, do not demonstrate unseen-site transfer. Neither the RF result nor these descriptive position statistics justify an outcome-tuned selector, a blacklist, or an operational change.
