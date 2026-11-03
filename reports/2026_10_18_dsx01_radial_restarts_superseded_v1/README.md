# DSX01 independent regional pipeline restarts

Report contains 6 worker results and 12 finite c-arm endpoints. There are 0 failed/missing/nonfinite arm or worker records; consult [audit](report_audit.json) and the [protocol](protocol.json) for planned counts. Partial reports do not imply completion.

Starts lie on a 5 km grid inside the 10 km disk centered at 37.906°, −122.545°. Localization is bounded by the same 25 × 25 km regional box. Existing conditional loss maps are preserved separately. Here circles show independently initialized association/localization runs and X marks their endpoints; no interpolated loss surface is shown. The solid paths are recorded within-round optimizer iterates; squares mark round anchors and dotted arrows show net displacement only. The c0 endpoint supplies the next round's common anchor, so the fitted-c round paths can be discontinuous. Archived acquisition, GLRT, and graph tracks are fixed. GPS is added after fitting for error measurement and plotting; no endpoint is selected using GPS.

Endpoint groups are descriptive complete-link groups of maximum diameter 0.5 km within each scan/method, shared across c arms. They are not certified distinct optima. Final objective colors are normalized separately within each method, scan, and arm; objectives must not be compared across different model families.

[Per-start numerical results](restart_summary.csv) · [Result hashes](result_bindings.json)

- [DSX01-S01: legacy_shared_phase](DSX01-S01/legacy_shared_phase/README.md)
- [DSX01-S01: linear_white_joint](DSX01-S01/linear_white_joint/README.md)
- [DSX01-S01: normal](DSX01-S01/normal/README.md)
