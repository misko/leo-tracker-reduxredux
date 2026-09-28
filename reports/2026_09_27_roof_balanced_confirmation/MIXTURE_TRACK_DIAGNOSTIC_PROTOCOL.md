# Posthoc fixed-position diagnosis of geometry regressions

The completed mixture geographic replay showed regressions on 53ce822d78d476ba and e76c229e9dc498b3 in both priors. Diagnose these two recordings because they regressed; this is explicitly outcome-selected diagnosis, not validation or a replacement evaluation cohort.

For each independent prior evaluate only its saved Doppler-only minimum, matched-mean geometry minimum, and mixture geometry minimum. Also evaluate the operator-supplied roof reference independently once per recording. Reuse identical coordinates when role labels coincide, but do not transfer fitted candidates between different positions. No new search, offsets around truth, weight tuning, calibration, timing correction, or track exclusion is allowed.

At every fixed position recompute the same full-catalogue, train-only zero-timing frequency shortlist and CFO. Use the original, matched-mean, and mixture reception models unchanged. The known reference is an oracle diagnostic only; its candidate IDs, weights, scores, and coordinates must never enter a location estimator or another position's fitted candidates. Propagation may be shared just as in the completed experiments.

Retain per-track candidate IDs, train-prior log probabilities, CFOs, training residual RMS, occupied-second weights, reserve counts, and candidate frequency/detection/conditional-ratio log likelihoods for every reception model. Derive separate posterior distributions after reserved frequency evidence and after joint evidence. Label MAP IDs as model associations, not decoded truth or verified satellite identity.

Reproduce every saved selected-position score for every reception model and arm within absolute 1e-7 before accepting output. Verify the sum of weighted per-track contributions reproduces aggregate scores. Bind the whole-cohort distance report, source replay, input/code/calibration artifacts, and this protocol. Preserve all previous artifacts and refuse output overwrite.

Report (1) whether the reference scores better or worse than each selected estimate under D and each joint objective; (2) which tracks contribute the largest score differences between mean and mixture selections; (3) whether those tracks change shortlist IDs, frequency-posterior MAP, or joint-posterior MAP; and (4) detection versus conditional-ratio increments. Use the telescoping shared-identity decomposition: detection increment=(D+detection)-D and ratio increment=(D+geometry)-(D+detection), not independently marginalized terms.

These checks can distinguish objective misranking, candidate changes, and score contributors. They cannot establish that a model MAP satellite is physically correct, that reference metadata are surveyed, or that an alternative estimator improves resolution. Do not choose a remedy by directly optimizing these known errors.
