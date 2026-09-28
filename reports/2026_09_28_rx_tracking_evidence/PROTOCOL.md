# Receiver tracking evidence preparation

This work follows the failed temporal-derivative pilot. It prepares evidence from existing derived caches; it does not rerun that model, change its evaluation split, collect RF, read raw IQ, or fit geographic position.

## Two distinct products

1. **Paired observation opportunities:** retain every recorded receiver probe, its qualification and source timing, including probes with no passing candidates. Group paired receiver windows explicitly; missing receiver data is missing, never a non-detection. Preserve candidate-level measurements and source identities. These rows have no asserted satellite identity. First/last passing-candidate times cannot be called satellite entry/exit times.
2. **Candidate frequency evidence:** recover normalized measured CFO through the public preparation contract, retaining original training/held masks and exact track/observation IDs. Predict only the already-frozen three candidate satellite IDs, at the original reference-conditioned receiver point and tau=0. Profile one constant CFO per candidate using original training rows only. Use fixed sigma=100 Hz, matching the original association protocol; no scale tuning or held-based ranking. Export per-candidate prediction, residual and normalized Gaussian log likelihood for each observation.

## Binding and checks before acceptance

Bind all cache hashes, input/analysis manifests, source links, original associations and the installed preparation/prediction implementations. Match prepared snapshot and evidence digests to the old associations. Check candidate IDs, observation timestamps, training masks and original training RMS/weights before accepting the exported frequency likelihoods. No full-catalogue candidate search is authorized. A provenance or reproduction mismatch is a failure to investigate, not permission to overwrite historical products.

Each extractor has one bounded invocation: one numerical thread, nice 19, 4 GiB address-space limit, 300-second wall deadline. Run them serially. Preserve errors and partial receipts; do not expand runtime or numerical search following failure. Pure synthetic component tests run first. Freeze executable and source hashes in launch receipts before extracting real evidence. Neither invocation evaluates a new reception model.

## What these products do not resolve

The old tracks and candidate banks remain detection-selected, research-exposed, and conditioned on the known roof point. Receiver mapping and beams remain provisional. Original frequency masks do not become fresh whole-recording validation simply because residuals are exported. Reconstructing the same inputs is an evidence audit, not a new model result.

Later reception conditioning must not use the same observation or overlapping paired source window as its frequency-scoring endpoint. Separate the reception-conditioning observations, Doppler-training observations and held-frequency target windows, keeping overlapping receiver windows together. Define target opportunity membership independently of held detections before interpreting a neither-receiver event or detection-order statistic. A candidate-consistent detection is still a proxy, not decoded satellite truth.

The ten-record inventory contains four 10 MHz, three 2.5 MHz, two 5 MHz and one 7.5 MHz recording. A future whole-record split must cover every evaluated rate in training; 7.5 MHz cannot simultaneously supply independent training and evaluation recordings in this cohort. Choosing a new split after the earlier result is exposed research and must not be presented as blind confirmation.

## Completion criterion

Deliver hash-bound opportunity and frequency products with reconciled denominators and tested joins, or a precise recorded blocker for either product. Report which requirements for a target-specific detection-order experiment remain unmet. Do not claim tracking-confidence or localization improvement from preparation alone.
