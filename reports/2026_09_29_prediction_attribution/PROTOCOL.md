# Exact predictive-score attribution

Reuse all 15 frozen out_of_pool targets, inputs and positions. No new fitting,
scan selection, track exclusion or location selection. Compare N24 with the
equal N8 mixture. Integrate timing at 32 Gauss-Legendre nodes per bank interval,
and replay against the previous independently audited 32-node scores to 1e-7.

For latent state z (timing, plus N8 component where applicable), prior p(z),
track likelihoods L_i(z), and posterior q(z), use the exact discrete identity
log Z = sum_i E_q[log L_i] - KL(q||p). Attribute the log-score difference to
track expectation differences and the remaining negative KL difference.
This is a posterior-dependent diagnostic, not a causal leave-track-out effect.
Group track contributions by RX and exact RF. Report posterior signal
responsibilities to distinguish background rejection from stronger track fit.
Do not use target-derived rankings as exclusions or corrections in this run.

Gate all 15 results on scalar replay, prior 32-node replay, and reconstruction
error <1e-7. Audit attribution stability using 16/32 nodes: track contribution,
KL difference and signal responsibility changes must each be <=0.01. Preserve
failures; do not aggregate unqualified results. Bound subprocesses to 180 s,
three concurrent workers. These are explored, site-conditioned data and an
unsurveyed reference, not blind validation or proof of sub-km accuracy.
