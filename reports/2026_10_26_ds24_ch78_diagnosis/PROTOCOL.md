# CH7/8 diagnosis round 2

User authorized parallel SOL high investigations of detection loss, receiver versus satellite residuals, and matched-evidence localization. One new SOL high agent owns detection. The session rejected further spawn/resume attempts with `agent thread limit reached`; root owns residual prediction, matched evidence, integration, review and publication. No new RF or production change is authorized by this experiment. QNAP remains read-only.

## Common controls

Use existing DS24 10 MS/s recordings and original causal banks. GPS is excluded from inference, nomination, parameter selection and RF qualification; release geography only after sealed inference. Fixed-assignment refits are mechanism tests, not end-to-end regional association reruns. Every position comparison includes matched c=0 and fitted-c; original identities, aliases, nuisance support and other priors remain fixed. Each starts at regional center [0,0] in the 25×25 km box centered 37.906, -122.545, with five phase refreshes and 48 position iterations. Whole held-family references use their causal prior mean. No location-specific offsets, post-scan TLE, stationary position pooling or GPS-selected winner.

## Detection

SOL freezes a separate protocol for eight paired windows: chronological DS24-0010 and0011, CH1/4/7/8, closest processed visit to midpoint, both receivers. Test complete blind historical acquisition/search against known injected timing/frequency diagnostics. Both pilot edges are represented. Fixed original data replay parity precedes injection. Recorded background is not assumed pure noise; digital injection cannot identify analog RF-input sensitivity. Preserve every failed/missing slot and report known-truth controls separately. No whitening sweep in this round.

## Residual prediction

Use first four chronological common usable DS24 cases (0010,0011,0012,0013), a development panel rather than a new-location validation set. Nominate the largest retained curved family present on both receivers by total point count then NORAD, before new fits. Retain explicit no-support cases. Three masks: omit that whole family; omit only its RX1 factors; omit only its RX2 factors. Remove matching predictive factors as well as curved values from training position and calibration. The latter two masks let the opposite receiver's family evidence inform its phase; the whole-family mask uses causal phase/orbit priors.

Compare current model with the existing frozen `sharedRF50` RX1 smooth correction (10 s basis spacing, 5 s width, 50 Hz prior at 11.5 GHz); do not tune its scale. Reuse verified joint predictive covariance and crossed endpoint scoring. Four cases × three masks × two models × two c arms =48 cold fits and96 fixed-position scores. The same-predictor crossover distinguishes support for position movement from simply adding predictive covariance. Report target RX and channel-group marginal scores as nonadditive diagnostics, including CH7/8; no independent-witness claim for multiple channels on one family. Check held-response redaction.

The main advancement screen uses whole-family holdout: both c arms must improve joint own-model prediction in every supported case, total gain>=10 in each arm, and both predictors' summed movement scores must be positive in each arm; all training and fixed-position phase/precision checks pass. This is a fixed development screen, not calibrated evidence or a guaranteed geographic benefit. RX-specific masks diagnose mechanism; they do not override a failed screen. Native RF noise and graph/label/support metadata have prior full-data exposure. Gaussian moment scores condition on train-only position and approximate Student/Gamma tails; position uncertainty is not integrated. Negative evidence ends this branch without further hyperparameter sweeps.

## Matched evidence

Use the same four cases. Reconstruct full saved graph assignments and original same-arm precision packets. This deliberately freezes empirical noise and nuisance-prior precision to separate data geometry from precision feedback; packet, graph and support are inherited from the original full-data fit, so it is a conditional mechanism control, not a blind channel-only algorithm. Remove all predictive factors for every comparison in this branch.

For each case retain full curved, low curved and high curved controls. For three predetermined seeds, downsample the larger band uniformly to the smaller band's count (count-only control); additionally match both bands within satellite-family × receiver ×20-second bins, choosing min(n_low,n_high) original points per cell. Keep the complete original nuisance coordinate layout and row support. Never fabricate or duplicate measurements. Counts, cell allocations and native IDs are frozen before fitting. If any mask has no usable data, preserve unavailable status without replacement. The seed is2026102602 plus case suffix plus replicate index. Each c pair uses identical masks. All covariance/alias/unit checks are retained. These deliberately reduced masks need not pass production graph support gates, so results are diagnostics, not candidates for adoption.

At most24 fits per case (96 overall), each numerical worker has a600-second cap. Each residual worker has a300-second cap. Up to four BLAS1 CPU workers; no multi-hour campaigns. Match source and input hashes at start/end, preserve failures and phase nonconvergence, and report geography only after all RF outputs seal. Compare count-only and time/family/RX matched effects; repeated subsamples are not independent scans. Channel halves can differ in antenna illumination, transmitter activity and residual systematics; equality of counts cannot identify all causes.

## Deliverables

Publish Markdown report, figures, all outcomes, tests and lean source/hash provenance to remote main under the user's standing instruction. A correction advances to operational regional evaluation only if independently supported. A negative or inconclusive result is retained, not converted into a GPS-driven policy. No new ALGO release is implied.
