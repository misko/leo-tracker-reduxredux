# Saved recovery identity audit

Read-only comparison of all15 requested windows and all693 frozen original observations within them. Include complete original fitted-c, fixed profile fitted-c/c0, expanded profile fitted-c/c0, and b1000 profile fitted-c/c0 protocols. Original c0 is unavailable, not imputed. No per-source/per-window method choice, new model/objective calls, fit, CFO score, held score, position/reference read, RF or production operation.

For each window retain N, assigned/unassigned, every assigned catalogue-ID count, dominant ID count/N and count/assigned, number of IDs with≥3 assigned points. Dominance is descriptive, not inferred truth purity. Multiple physical emitters may occur within a coherent window, and a dominant model ID may still be wrong. Satellite labels on unassigned rows are excluded from identity counts, but those rows remain in N.

Adjacency uses stable chronological order of ALL observed window rows. Count identity changes only for consecutive observed rows that are both assigned, in exactly the same receiver/channel/actual-RF lane, separated by≤1 second. Unassigned rows, different lanes and larger gaps break adjacency. Report eligible pair denominator and exclusions, not just switches. No assumed emitter persistence or new likelihood follows from this diagnostic.

Preserve the existing descriptive strong-restoration threshold: net assigned gain/original missing≥80%, always with the original fixed denominator. This does not assert same-emitter recovery or verified labels. Both RF arms retain all saved outcomes, including rejected KKT endpoints; this is not a new strict selector.

Ordering proof: source length and exact full ordered time vector for every NPZ; original assignment/model-ID labels checked against frozen context; b1000 also persists exact IDs/RX/channel. Older original/fixed/expanded NPZs do not persist row IDs, so equal-time row swaps cannot be independently excluded from those arrays alone. Bind their original producer source and common observation ordering; disclose the limitation rather than claim equal lengths prove identity.

Freeze the35 NPZs,3 metadata files, producer source, audit source/tests/protocol before aggregate computation. External120s TERM/125s KILL. Component tests cover retained denominator/loss, unassigned labels, net restoration, adjacency exclusion semantics, exact ordering and empty/invalid membership. No original seal changes. Output105 rows, all model-ID histograms, source ordering checks and a comparison plot; no promotion or truth-selected weights.
