# Frozen trajectory mixture transfer to three complete B02 blocks

Use all four scans in DS9-B02, DS10-B02 and DS11-B02 from the sealed quad selection. These are existing development recordings, not untouched test data. Selection uses block identity only, not radio fit or geographic outcomes. Preserve existing independent-track filtering and every eligible track. No orbit propagation, localization fitting, GPS, IQ read or new RF.

Reuse the frozen mixture and robust-control implementations and parameters: sigma 100 Hz primary / 300 Hz control, six deterministic EM starts, 100 iterations, six-point/three-second component support, training-only 4 log(n) complexity rule, and 8 log(n) penalty ablation. Failed or unsupported mixture fits fall back to their single Gaussian. Report any robust-control failure; do not impute a score.

Repeat two-way alternating folds. Add a stricter forward temporal split: first chronological half trains, remaining half is held; this is extrapolation and can reveal failures hidden by interleaved samples. All preprocessing and model choice use training observations only. Track construction itself already used the full capture, so this is not fully causal online validation.

Report pooled and per-scan gain against Gaussian and robust single curves, raw and selected mixtures, unchanged tracks, selected-component support, and failures. Each full block remains the grouping unit; do not label tracks or folds independent trials. Report both scales and both split types without choosing the favorable one.

New transfer gate, distinct from the failed pilot median gate: primary selected-policy gain versus robust single must be positive in each dataset for both split types, at least three of four scans per dataset must improve for each split type, and every robust control must converge. A pass only permits a bounded localization integration pilot; failure blocks automatic promotion. Do not revise this gate after results. Workers run sequentially under the shared lock with single-thread libraries and a 90-second cap per scan.
