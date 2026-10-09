# Timing diagnostic frozen; execution pending

The preparation README records its earlier, unfrozen state and remains bound
unchanged. The reviewed protocol is now frozen with SHA256
`206a0c255c766303a6f82342b9065590a6d95bc5f667b2a29f359a939cde2558`.
Independent parent verification confirmed all 5,581 source hashes and the six
saved states. No attempt receipt exists and no recording replay has run.

Review caught and fixed an instrumentation bug before execution: the production
objective modifies the prediction array in place, so capturing it by reference
would double-count receiver frequency terms during decomposition. The diagnostic
now copies the orbital prediction before that modification. Its synthetic replay
exercises the actual objective with nonzero receiver, baseline and static RF terms.
Failure reporting preserves completed rows and call counts; derivative comparisons
require the positive and negative probes to match the base visibility, interpolation
cell and alias branch.

Execution remains queued after experiments 110 and 111, using a free slot under
the two-worker limit. This is a six-state mechanism diagnostic, not a localization
improvement trial. Production B7, acceptance gates and recording inputs are unchanged.

The [plan and diagnostic diagram](PLAN.md) describe the hypotheses and limits.
Horizon margins are not implemented; the available mask and fixed-mask score
comparisons must not be represented as the full proposed instrumentation.
