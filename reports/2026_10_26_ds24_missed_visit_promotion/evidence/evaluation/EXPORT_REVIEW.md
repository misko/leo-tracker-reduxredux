# Post-seal export coordinate audit

The current `held_position/export_endpoints.py` expresses curved aliases as total native-CFO lift, but predictive aliases as only the entry-relative lift. These coordinates differ whenever the predictive graph itself has a nonzero native lift. Correct total predictive lift is round((track value−native measured CFO)/PERIOD)+entry alias.

This does not change positions, objective replay, membership IDs or satellite labels. It can falsely report a physical alias change when a retained owner changes predictive/curved role. The independent evaluator's `replay_endpoints.mapping` already normalizes both roles to total native lift. Use that coordinate for attribution; do not edit source files already bound into an active inference protocol. If the exporter needs revision, preserve it and add a separately sealed postprocessing version.

The independent replay also reconstructs the saved prior/model directly rather than calling `recovery.context`, which requalifies the prior by optimization. Fixed-endpoint replay needs no new prior/position fitting. Capped cases with incomplete read receipts remain nonqualifying, while their failure stays in the full intended cohort.
