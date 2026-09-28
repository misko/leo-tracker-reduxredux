# Expanded roof directional experiment

Frozen before examining reception outcomes, 2026-09-27 around 04:04 UTC.

## Corpus and authority

`manifest.json` freezes the newest 12 of the 27 capture-pose companions found at selection time, ordered by capture UTC: 02:28:49 through 03:46:31. First eight calibration, final four holdout. Exclude incomplete or unqualified public analysis bundles without replacement. All selected scans occur after the documented cable repair; this does not independently guarantee hardware stability. Verify companion/authority/source digests and complete simultaneous dual-RX probe coverage. No new recording, RF replay, production change, or remote write.

The metadata remains operator-supplied WGS84 roof coordinates, nominal opposite east/west receiver tilts, provisional software/physical mapping, unknown surveyed altitude and RF phase centers. It is not upgraded to a surveyed GPS fix by this experiment. Use zero altitude only as an explicit propagation approximation.

### Readiness amendment, before reception scoring

The initial 12-scan inventory had five ready calibration scans and only one ready test scan. Preserve it as the freshness panel, with no retroactive replacement. A separately frozen `evaluation_manifest.json` therefore defines a readiness-selected cohort: newest ten complete public analysis bundles among the same 27 captures/capture-time cutoff, first six calibration and last four holdout. Selection reads only metadata and complete metrics-manifest presence, not reception or location results. Full public input loading subsequently verifies coverage. The 02:50 scan became complete between inventories and is explicitly recorded as such, not silently changed in the first inventory.

The available cohort spans 02:07:37 through 03:25:21. Its test scans are 02:50, 03:04, 03:11, and 03:25 UTC. The 03:04 and 03:11 sample rate (5 MS/s) is absent from calibration; include sample rate as a common nuisance in M0/M1 and report an additional no-refit sensitivity on only test rates represented in calibration. Do not select a preferred result afterward.

## Scope and endpoints

1. Extend paired-compatibility counts and separated-time controls to this independent newer subset. Candidate matching uses the previous fixed 2.2 microsecond modulo-frame and 10 kHz alias-aware CFO tolerances. Estimate common RX frequency bias on calibration only. Match by frequency/epoch proximity, not largest counterpart margin. Compatibility is not decoded satellite identity.
2. Construct persistent tracks and Doppler-only satellite hypotheses without using cross-receiver reception to select a satellite. Existing detection/track construction remains selection-conditioned; do not claim a fully independent antenna-power likelihood.
3. First perform a **truth-conditioned directional feasibility diagnostic**: use roof position to compute Doppler associations and arrival directions on calibration and holdout. This asks whether available geometry is associated with reception; it cannot demonstrate unknown-position recovery. If feasible within the bounded run, evaluate independently generated geographic branches separately; never share reference/Sacramento/Reno candidates.
4. Primary endpoint: probability that a detected anchor candidate has a compatible counterpart on the other receiver in the same observed probe. Missing probes are exclusions, not nondetections. M0 uses channel/edge, anchor receiver, and log anchor GLRT margin. M1 adds signed posterior east component (positive for RX0 anchor, negative for RX1). Fixed ridge strength 1; calibration-only standardization. Unit total weight per track, plus equal-scan reporting. GLRT margin is a detection proxy, not calibrated RF power.
5. Secondary endpoint: log ratio of matched candidate margins, always RX1/RX0, among both-detected compatible anchors. M0 uses channel/edge/anchor receiver; M1 adds east component. Report this censoring explicitly: the endpoint cannot explain signal absence or estimate an unbiased beam pattern.

Use training Doppler samples for association weights, with a bounded zero-timing model initially; report candidate ambiguity and model simplifications. Reception holdout scans never tune model penalties, matching tolerance, physical mapping, association noise scale, or subset selection. Residual candidate/track selection bias is a limitation, not cured by scan holdout.

Reception endpoints use only observations excluded from each track's Doppler-training mask, in both calibration and test scans. Join using the public source-group/sample-support/UTC provenance tuple, excluding ambiguous joins. Persistent-track construction itself uses all candidate evidence and detection gating; this remaining conditioning must be reported. Channel/edge nuisance means a joint categorical lane effect, not only two additive terms.

## Controls and claims

Fixed channel/edge-preserving half-series time shift for matching; calibration-direction permutation and heldout track-direction shuffle for M1; physical mapping sign reversal with calibration parameters fixed. Do not select the physical mapping by holdout performance. Cluster uncertainty at scan level, not individual-frame level; only four test scans means intervals are descriptive and low power.

Report per-scan complete opportunity accounting, usable track/anchor counts, calibration parameters, test loss deltas, and all unavailable stages. Failure of M1 to improve does not prove geometry contains no information; uncertain associations, unknown antenna pattern, common-pilot ambiguity, proxy censoring and provisional orientation can weaken it. A positive truth-conditioned diagnostic is not a geographic accuracy improvement. Actual location recovery requires independently rerunning search without using the roof coordinate or a truth-derived candidate union.

Pre-scoring audit controls: report one-vote-per-probe CFO-bias sensitivity alongside the original candidate-pair-weighted calibration. Primary detection is a conditional-anchor endpoint: reciprocal anchors can legitimately supply both conditioning directions but are correlated, not independent samples. For the secondary log-margin-ratio endpoint, additionally refit/score with exactly one row per unordered matched candidate pair, deterministically preferring the RX0 anchor. This checks duplicate physical-pair weighting rather than tuning the outcome. Bootstrap resamples whole scans and retains the equal-track loss estimand.

Additional pre-scoring support sensitivity: repeat the unchanged models on tracks spanning at least 30 seconds, using full source-track timestamps for this eligibility rule. This checks whether the many very short tracks obscure a geometric relationship. It is a separately labelled sensitivity, not a replacement selected according to test performance.

Do not wait on a multi-hour analysis campaign. This is a bounded experiment over existing published analyses. Preserve caches and evidence digests for reproducibility.
