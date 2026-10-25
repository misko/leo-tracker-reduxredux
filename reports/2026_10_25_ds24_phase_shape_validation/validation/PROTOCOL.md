# Later fast-recording validation of the frozen RX1 candidate

This is a research panel, not a new dataset or a change to DS24. Membership is
the first eight chronologically ordered complete, metadata-qualified 10 MS/s
jobs in the previously saved post-cutoff inventory. Selection is frozen before
full contract validation and geographic evaluation. Failed validation or
inference is retained in the denominator without replacement. Canonical
capture timestamps, full public contract identities and raw authorities must
be verified before fitting. Prior error exposure is audited separately from
production inference completion.

The reference is freshly reconstructed ALGO02-v1 plus qualified causal signed
timing means and equal-assignment-prior family cavity, using the same existing
implementation as the DS24 reference. Original graph configuration, regional
25×25 km box centered at 37.906,-122.545, causal catalogue and priors are kept.
No prior production position is reused. Existing GLRT contracts are inputs;
there is no IQ processing, collection, satellite whitelist or evaluation GPS
in inference. All catalogue epochs and archive collection times must be causal.

The sole candidate is the already frozen `fast_rx1_rf50`: 31 Gaussian basis
coefficients centered at 0…300 s in 10 s steps, width 5 s, 50 Hz prior scale at
11.5 GHz, shared RX1 loading proportional to RF. Its affine projection and
expansion reuse the unchanged original source. Original reference observations,
satellite assignments, aliases, powers, masks, noise model, source constants,
other priors and predictive evidence remain fixed during this comparison.

Both c=0 and fitted-c receive matched data, candidate sets and budgets. For the
candidate, the original cold refit starts at regional [0,0] and zero phase
references, with five phase rounds and 48 optimizer iterations each. A separate
matched cold baseline control uses exactly that same fit budget and start with
no RX1 addition. It is diagnostic, not a new reference selection rule.

The primary policy stays unchanged from the preceding candidate: adopt the
RX1 pair only if its original curved/predictive RF and phase gates pass in both
c arms; otherwise retain the exact freshly reconstructed reference pair.
Do not select using GPS, frequency improvement, which c arm helps, or the
matched cold control. Postfit association membership and losses of baseline
IDs are reported explicitly; they are not silently turned into a new policy
gate. A numerically failed trial retains the qualified baseline if available.
A failed baseline is unavailable, not a zero error or a replacement recording.

Maximum four isolated case processes, one BLAS/OMP/MKL thread each, 600 s per
case and 1,200 s cumulative campaign wall time. Existing per-stage maxima also
apply, with the remaining global/case budget taking precedence. Timeout kills
only the newly created stage process group, including elevated read-only
preparation children. No retry, seed change, rescue, altered inference budget,
case replacement or parameter search. Preserve partial outputs and every
stage receipt. These are bounded existing-GLRT analyses, not an RF campaign.

Source/input hashes and independent preflight must pass before execution.
Final RF decisions are sealed before geographic evaluation. Evaluate at the
established site 37.849061591561885,-122.48574968092912, separately from inference;
record available deployment evidence and the limits of this site assumption.
Report primary paired errors, matched cold controls, all selected-case failures,
both c arms, frequency RMS and score changes, unique likelihood/postfit
membership and runtime. Different observation sets across failed/unavailable
cases must not be compared as if matched. Later same-site performance does not
establish transfer to different locations.
