# Successor execution plan

1. Admit a new manifest only when all listed sessions have completed tracking
   and matching causal-cache receipts. The supplied cache root is verified by
   session ID and state-cache digest.
2. Generate the portable plan. It creates `joint-all<N>` from the actual
   manifest count and keeps all sessions in every joint task. There is no
   train/validation/test split for this full-corpus evaluation.
3. Review the generated plan before explicitly running `--mode portable
   --execute`. The adapter serializes no result replacement and retains the
   reviewed portable runner's equal whole-session weighting for joint tasks.
4. After a digest-sealed successor rate finalist and exact gate, implement the
   generated follow-up contract for the cap-800/rate screen, repaired
   session-scale/residual diagnostics, and shared-NORAD accounting. They must
   bind the generated `joint-all<N>` parent instead of any 20-session artifact.
5. Run geometry/cone work only after a fresh receipt-bound geometry export for
   the sessions admitted in `geometry/plan.json`. Evaluate both mappings and
   the learned, fixed, staged, and local-fitted cone families.
6. Use `postseal_evaluation.py` only after `portable/execution.json` is sealed
   and complete. It is the reference boundary. The legacy L-BFGS-B model is
   accounted for as rejected and has no execution step.
