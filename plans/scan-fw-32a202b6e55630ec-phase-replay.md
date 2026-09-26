# Phase-recovery replay plan: scan-fw-32a202b6e55630ec

Prepared 2026-09-26. Status: **plan only; no numerical replay or new RF collection has been run for this task.** Execution is intended for SOL (`gpt-5.6-sol`) workers after the user starts the execution phase.

Objective: re-evaluate every approach in the preceding phase-recovery review on this recording, using audited capture coordinates and corrected GLRT acquisition. Deliver an approach/report/outcome table, comparable held-out measurements, and visual evidence of successes and failures. Historical failures are hypotheses to retest, not expected outcomes to reproduce.

## 1. What is already verified from metadata

Metadata was read directly; raw-IQ integrity and RF validity are still execution gates.

| Item | Observed value |
|---|---|
| Recording | `scan-fw-32a202b6e55630ec` |
| Manifest | `/srv/bulk/leo/scanner-adaptive-recordings/scan-fw-32a202b6e55630ec/manifest.json` |
| Manifest document digest | `sha256:b381f62da5b5490e43790b69e2947919ad9fee6441b642ac04e7af1be487993a` |
| Schema/layout | Manifest v14; receipt v6; event v3; chunk v12; `ci16_le`, `sample_receiver_iq` |
| Radio | `radio_pluto_5d4d`, simultaneous RX0/RX1 |
| Rate / configured bandwidth / gain | 10 MS/s / 10 MHz / manual 40 dB |
| Device-counter session span | 300 s, beginning at counter `492145132025` |
| Estimated UTC start | 2026-09-26 12:20:02.303983 UTC |
| UTC uncertainty | First-sample bracket width 364.640303 ms; not sub-millisecond absolute timing |
| Stored payload | 2,214 visits, each 1,200,000 samples per RX = 120 ms; 265.68 s valid payload |
| Coverage | CH1 upper: 579; CH2 upper: 563; CH3 upper: 547; CH4 upper: 525; no lower-edge visits |
| Storage | 2,214 compressed chunks; 12,081,522,714 compressed bytes; 21,254,400,000 uncompressed bytes |
| Receipt accounting | Zero transport-missing, unclassified, and unreceived-tail samples; 34.32 s transition-invalid time; valid duty 88.56%, below configured 90% target |
| Candidate boundary population | 552 adjacent same-target event pairs; payload gaps 0.3–5,247 microseconds. These are metadata candidates, not yet same-emitter or phase-continuous pairs. |
| Existing analysis | v8 binding `5808b8a9d1729e606dbee610f9af5cbd93c87caa8579b7672e4f6c7e404a2336`; 2,214 visit rows |
| Existing probe geometry | 20 ms probes, 120 ms stride, RX0 and RX1, eight candidates, fractional GLRT margin gate 0.025 |

Existing analysis directory: `/srv/bulk/leo/scanner-adaptive-analysis/scan-fw-32a202b6e55630ec/5808b8a9d1729e606dbee610f9af5cbd93c87caa8579b7672e4f6c7e404a2336/`. Its two probe rows per visit correspond to receiver evaluations; do not mistake them for dense coverage of each 120 ms dwell.

The working checkout is behind local `main` for the recent GLRT repairs. At planning time, this checkout is `a887eec1`; local main is `e1a24b20`. Two prior report directories contain untracked work. Preserve both and use an isolated execution worktree. Pin all implementation commits and source hashes; do not assume `/opt/leo-tracker/current` identifies the adaptive worker's runtime. The inspected binding has no explicit release SHA, so establish its producer from publication/deployment evidence before assigning it to an old/corrected comparison.

## 2. Gate A: resolve capture and GLRT defects before scoring methods

Recent evidence on local main:

- `reports/2026_09_25_glrt_timestamp_contamination.md`: timestamp words masqueraded as dual-RX IQ, sometimes dominated a GLRT frame, and produced false shared-signal evidence. Identified words decoded to the expected counter plus two. Diagnostic zeroing did not certify the rest of the recording or reconstruct missing RF samples.
- `reports/2026_09_25_glrt_tuning_verification.md`: zero-centered ±400 kHz acquisition missed signals under the actual native-rate tuning. Shifting the center alone could lose the other RX. Candidate retention could still miss the correct basin after frequency coverage was fixed.
- `847ebcaf936c808315cb723418e1a20546eaba34`: capture-aware search geometry, physically admissible template support, and bounded 22-anchor peer fallback; `4c6fd46e` documents live verification.
- `554e8403`: canonicalizes frequency-offset presentation. Displayed modulo offsets must not replace the absolute branch used for coherent mixing.

The user confirmed these are the intended recent issues; no additional fix was named. These findings concern other recordings. Their applicability to this scan must be measured. In particular, the timestamp diagnostic documents a defect and an experimental intervention, not proof of a deployed capture repair. Do not invent a corrected capture release from this receipt alone.

**Capture audit and deliverables**

1. Verify manifest, compressed and decompressed chunk digests, lengths, receiver packing, ordinal-to-visit mapping, and all event/counter intervals. Read through the current typed source port, using an additive report adapter only where older research helpers require arrays.
2. Trace source framing through the capture implementation, importer and reader. Identify the exact semantics of timestamp words: inserted metadata, overwritten RF rows, or another representation. Resolve counter offsets from evidence. Never delete rows or close time gaps speculatively.
3. Inventory counter-word matches and amplitudes across every visit, not only high-amplitude outliers. Require framing/counter evidence before classifying a row as non-IQ. Separately flag unexplained impulses, clipping, duplicate blocks, receiver crosstalk/copying, settling intervals and counter discontinuities.
4. Produce immutable derived validity masks. Primary scientific estimates use RF-valid support and reject transform/pilot windows touching unaccounted corruption. Mask-aware weighting is permitted only if validated for that estimator. Zero-fill known words only as a named sensitivity analysis; never call the result recovered IQ.
5. If filtering is used, expand invalid support by the filter impulse response and discard edge transients before any fit or holdout split. A timestamp impulse filtered first can contaminate many nominally clean samples.
6. Preserve three coordinates: compact storage index, authoritative device counter, and uncertain UTC. Use one device-counter origin for phase across visits; subtract integer counters before floating-point conversion. Keep gaps and retunes explicit. Source-span attestation and zero transport loss do not certify phase continuity.

Outputs: `capture-audit.json`, `visit-inventory.csv`, `validity-masks/`, `source-provenance.json`, and a capture coverage/contamination timeline. If counter mapping is unresolved, continue valid within-dwell work but explicitly block affected cross-dwell claims.

**GLRT verification and ablations**

1. Freeze one corrected code revision containing the geometry and regression repairs. Run relevant component tests plus independent direct/scalar scoring parity, fractional-epoch, frequency-translation, receiver-swap, and phase-reference invariance tests.
2. Compute pilot RF center from channel/edge and template; effective IQ center from actual LO plus only documented applied digital translation. Intersect uncertainty priors with usable bandwidth and the full eight-tone template. Never use a hard-coded zero center, 2.5 MS/s epoch, or another RX's CFO as the primary acquisition seed.
3. Distinguish independent blind acquisition, production peer-triggered stronger-anchor acquisition, and explicitly timing-assisted diagnostics. A peer triggering extra independent search is different from supplying its timing or frequency.
4. On a fixed metadata-selected diagnostic cohort, run a 2×2 comparison: legacy versus corrected acquisition, and archived versus RF-valid data. Apply identical validity treatment to exact and control templates. Also rescore frozen candidate coordinates to separate score changes from acquisition/selection changes.
5. Keep tuning-only, physically clipped wider coverage, stronger-anchor fallback, and bounded larger-shortlist trials as separate ablations. Apply expensive shortlist trials to a frozen miss/weak cohort, not a hand-picked recovered example. Log truncation, work counts and runtime.
6. Rebuild phase-blind detections, alias alternatives and candidate track families from corrected evidence. Persist actual acquisition CFO, residual CFO, absolute/lifted CFO and display CFO separately. Do not transplant old selected tracks or receiver offsets into the primary population.

Outputs: `glrt-audit.json`, `candidate-inventory`, `track-inventory`, `legacy-corrected-confusion.csv`, and frequency-search/epoch/margin plots. Reuse persisted evidence only after confirming producer and numerical parity. The historical 0.025 gate is a comparison threshold, not a newly calibrated false-alarm probability.

## 3. Shared experimental design

**Two questions, two denominators.** Report both end-to-end yield over all scheduled/eligible visits and estimator performance on identical acquired support. A method can improve acquisition without improving phase, or produce precise phase on very few visits. Report attempted, RF-valid, acquired, supported, phase-qualified and held-out-passing counts separately, with every exclusion reason.

**Census and bounded primary cohort.** Inventory all 2,214 visits and all 552 candidate same-target boundaries. Corrected baseline acquisition covers every visit; use the existing first-20-ms schedule for a like-for-like census. Dense phase extraction then covers whole 120 ms dwells in a frozen 128-visit primary cohort: four targets × eight equal device-time blocks × four hash-ranked visits, seed `20260926`. Selection uses metadata and RF validity only, not GLRT or phase success. Keep any shortfall explicit. The first two time blocks are development; the remaining six are locked evaluation. Reject windows or boundary pairs crossing that split. Insufficient independent evaluation units mean descriptive results, not a manufactured significance claim.

Add a separately labeled diagnostic cohort of strong, weak, RX0-only, RX1-only and neither-RX candidates, frozen from corrected GLRT before looking at phase. It must not replace the primary population. For cross-dwell methods, use all phase-blind qualified boundaries/track visits that fit the measured runtime budget, with explicit completed/eligible counts and deterministic checkpoint continuation. Do not use only the prettiest or longest phase sequence.

On each primary-cohort dwell, acquire six non-overlapping native 20 ms probes at offsets 0, 20, 40, 60, 80 and 100 ms, on both receivers, before phase evaluation. Preserve all admitted candidate branches and reconstruct complete actual-frame lattices only within their qualified support. Dense acquisition is a separate yield comparison to the sparse persisted schedule. Phase restoration must retain a common sample reference across those containers; an independently selected epoch/CFO does not authorize an arbitrary fitted phase intercept. Report ambiguous overlapping candidate lattices rather than merging them on visual phase agreement.

**Fair support.** Run compatible estimators on the same raw windows, timestamps, validity masks, acquisition candidates and symbol partitions. Retain each method's native acquisition result as a separate end-to-end comparison. Use paired common-mask errors for head-to-head comparisons and own-mask yield for availability. Do not silently remove failed dwells from averages. Prefer per-dwell summaries, grouped by channel and time; correlated frames, overlapping windows and adjacent boundaries are not independent trials.

**Validation and model selection.** Freeze settings on development support. On evaluation visits report both disjoint-symbol/frequency or random non-overlapping holdouts and forward-time prediction. Label random held-out reconstruction separately from causal forecasting. Transform and filter supports, not just window-center labels, must be disjoint. Fit no per-evaluation-window phase intercept to make a predictive score pass. Historical in-sample fits remain displayed but never substitute for held-out performance.

**Controls.** Exact versus matched-coordinate rolled/deranged/opposite-edge references; wrong receiver-time and receiver-pair controls; within-track order permutations; timestamp/impulse-only and noise synthetic inputs; known phase/CFO/rate/delay injections. Wrong-time offsets must avoid measured recurrence peaks (historically 20/40/60 ms), with choices frozen from development data. Detection-search negatives undergo the same nuisance search and candidate budget as positives; fixed-coordinate pilot-specificity controls are labeled as such. Controls are not a universal false-alarm calibration.

**Rate and phase units.** Primary processing is native 10 MS/s. Check every old helper for hard-coded rate, receiver/path, Qin edge, layout, dwell length, frame-lattice rounding, filter delay and timestamp conventions. Use physical durations when translating 2.5 MS/s reports. Phase outputs identify ordinary 2π, modulo π, timing/code phase, RX differential phase, and response-normalized residual phase explicitly. Never rank these different observables by one pooled R value.

**Bandwidth ablation.** Derive 2.5 MS/s from the same native samples with documented anti-alias filtering. Recenter only through an explicit sample-time-consistent frequency transform, restoring the phase reference exactly once. Confirm the complete pilot/common physical band survives for both RX paths. If it cannot, mark the narrow-band pilot comparison inapplicable; raw zero-centered decimation is not an equivalent experiment. Record filtering support and use identical physical training/held windows.

## 4. Complete method ledger and required visuals

The numbered rows cover all 30 entries in the previous review. Multiple old reports can describe stages of one estimator; preserve their variants rather than executing copied scripts with incompatible defaults. Every row must end as completed, failed, not applicable with evidence, or incomplete with outstanding work—not silently omitted.

| IDs / historical approach | Replay on this scan | Primary evidence and visual |
|---|---|---|
| 01 Integrated CFO boundary bridging | Integrate phase-blind local CFO models on device time; compare one phase reference with separate references. Separate within-dwell, same-target adjacent and retuned boundaries. | Held boundary error and continuity residual versus actual gap; overlay capture defects. |
| 02 Frame-local Qin phase | Exact-template frame phasors, disjoint-symbol prediction and frame-quality controls on each RX. | Frame phase/uncertainty timeline and exact/control held-symbol error distributions. |
| 03 Adjacent-frame correlation | Constant-increment prediction within 20 ms containers, plus all consecutive valid frames in the dwell. Do not reset the phase gauge invisibly between containers. | Lag concentration and held prediction error versus span. |
| 04 Prompt phase versus integrated linear Doppler | Reproduce phase-reference-restored PNT discriminator and explicit reset episodes. | Innovation trace and episode-duration survival curve, with frequency-only reference. |
| 05 Five-state phase feedback | Matched phase-feedback on/off variants with identical seeds/frequency observations. | Paired held-out CFO/rate error, uncertainty coverage and phase innovations. |
| 06 Ordinary 2π long tracking | Ordinary tracker inside each verified continuous dwell and demonstrably eligible adjacent chain; reset at qualified discontinuities. | Accepted-update fraction, resets per valid second and longest supported run. No fabricated 60 s continuous recording. |
| 07 Full Qin phase slope | 300-symbol/eight-tone frame CFO, versus 64-symbol GLRT and held symbols; retain half-frame/tone-deletion checks. | Local phase ramp, frame CFO and held error. CFO recovery remains separate from continuity. |
| 08 Offline binary-π batch fit | Reconstruct actual complete frame lattice; doubled-phase fit, binary state and coherent stack, including historical 80 ms support. | Ordinary/modulo-π residual overlays, held-symbol error and stack efficiency. |
| 09 Causal modulo-π filter | Frozen ordinary/modulo-π ablation on the complete cohort, not only windows selected as modulo-π successes. | Paired RMS, update and reset plots; distinguish branch choices from physical resets. |
| 10 Five-state modulo-π PNT | Phase/CFO/rate/fractional timing/timing-rate updates inside independently initialized arcs. | Lock yield and forward-prediction diagnostics against a direct local CFO fit. |
| 11 Production multi-window qualification | Reapply inner phase-lock and full 75 ms segment gates separately. | Qualification funnel and channel/time heatmap; exact denominators. |
| 12 Short segments versus long GLRT lines | 50/75/80/100 ms local arcs where support permits; compare with phase-blind across-visit CFO associations on true elapsed time. | Local rate versus long rate, uncertainty and capture-boundary overlays. |
| 13 Scanner retune-bounded tracking | Reproduce scanner qualification within each visit using independently confirmed pilots; no state continuation through a retune by default. | Scan-wide qualified-span raster, including GLRT-positive/phase-negative visits. |
| 14 Semi-coherent pooling | Independent per-frame nuisance phases over 20/50/100 ms; even symbols train, odd validate. | Held frequency support and rate repeatability versus integration length; labeled frequency-only recovery. |
| 15 Capture/reset mechanism | Compare phase/CFO/timing changes with verified non-IQ rows, device gaps, profile transitions and storage edges. | Event-aligned residuals and jump-versus-gap plots; correlation alone does not prove emitter changes. |
| 16 Robust jump and phase-gated filters | V2, trailing-20-ms robust line, jump filter, phase-gated jump filter and offline smoother; explicit local arcs. | Common-mask predictive-error versus utilization plot and lock-duration distributions. |
| 17 V3 phase-safe tracking | V2/V3 matched seeded and end-to-end variants, preserving published semantics and branch choices. | Acquisition/track/phase transition matrix, held CFO error and retained/lost phase arcs. |
| 18 V4 seed/control correction | Seeded multi-mode V4 and unchanged tracking core versus V3, retaining ambiguity and all mode outcomes. | Recovery/loss matrix; new phase locks reviewed individually with controls. |
| 19 PSS/SSS carrier phase | Native-band correct-tuning templates; inter-frame phase before any unwrap; noncoherent frequency baseline. | Phase increments and held errors; blind SSS versus PSS-timed SSS explicitly separated. |
| 20 PSS timing phase / weighting | Within-dwell 62.5 ms timing windows; independent PSS timing corridors across visits; equal, score and robust weighting ablations. 125/250 ms uninterrupted windows are unavailable in an isolated 120 ms dwell and must not be synthesized across gaps. | Timing residual in microseconds, timing-track fragmentation and branch-aware CFO comparison. Keep timing phase separate from carrier phase. |
| 21 Dual-RX pilot double difference | Correct residual-CFO restoration, phase-blind one-to-one RX pairing and two-signal association. Audit common-mode cancellation assumptions. | Per-signal RX differential phase and two-signal double difference versus device time, held prediction and permutations. |
| 22 Double-difference window/common-frame tests | Nominal 23/47/95 ms support; common-frame direct products versus separately timed fits. | Availability versus window length, common-frame counts and held next-visit errors. If no two-signal support, report unavailable rather than force pairs. |
| 23 Response-normalized disjoint-band phase | Train channel response on development/training support, evaluate disjoint groups and held time; redo index/sign/frequency perturbation checks. | Raw versus response-normalized phase, A/B consistency and perturbation heatmap. Never label normalized R as raw phase. |
| 24 Direct dual-RX IQ | Raw, constant-CFO, and CFO-plus-rate variants, zero fitted relative delay, identity response and no phase intercept; random-disjoint and forward holdouts. | Same-scale traces, in-sample versus held R/error, same/wrong-time coherence. |
| 25 Aggregate and per-bin FFT | Full-bin Parseval parity; physical-overlap/magnitude masks; phase-only weighting; arbitrary-bin versus pilot-aligned phase. | Direct/FFT discrepancy, per-bin increment heatmaps, overlap/non-overlap controls. Extra pilot-aligned work is exploratory if absent from old method. |
| 26 Bandwidth | Matched native 10 versus derived 2.5 MS/s, plus valid physical bandwidth sweeps for direct, FFT, pilot and disjoint-band estimators. | Paired held error/R versus bandwidth and retained energy/support; no cross-session rate claims. |
| 27 Absolute phase across a track | Freeze all qualified dual-RX track families before reading phase; inspect every supported visit, both absolute and display-centered phase. | Full-track circular means, wrapped changes, permutations and local shape comparison; unwrapping never bridges an unobserved gap by fiat. |
| 28 Global-time adjacent-boundary transport | Frozen historical degree-2 frequency fit on both dwell interiors; exclude crossing increment. Also test causal previous-dwell-only prediction and fixed boundary-local fits. | All-boundary residual forest plot, error versus gap, model sensitivity, and joint-fit versus causal scores. |
| 29 Cross-track replication | Apply frozen boundary settings to all eligible track families/channels in the evaluation portion, grouping edges sharing a dwell. | Per-track/channel results and leave-group-out sensitivity. One scan is within-recording replication, not independent-session replication. |
| 30 Phase-assisted association | Evaluate phase evidence for RX pairing, then candidate-specific geometric residuals only where timing, array calibration and TLE provenance permit. Learn nuisance/calibration terms on development support only. | Pairing evidence and candidate likelihood change versus predicted geometric separation and measured noise. Preserve sign/cycle/TLE ambiguities. |

Recent PSS reports on main (`2026_09_25_dual_rx_10msps_pss_glrt.md` and `2026_09_25_five_glrt_tracks_pss_reconstruction.md`) belong to row 20 as additional baselines. Reproduce both independent PSS branch association and explicitly GLRT-conditioned branch lifting; the latter is not independent CFO validation. Their existence also means the original historical list should not be treated as the final code inventory.

Source reuse candidates: `tools/report_frame_local_phase_qualification.py`, `tools/report_within_segment_frame_phase.py`, `tools/report_pnt_phase_doppler_comparison.py`, `tools/report_pnt_kalman_comparison.py`, `tools/report_pilot_pnt_kalman.py`, `tools/report_subsecond_pilot_structure.py`, `tools/report_five_dwell_modulo_pi_qualification.py`, `tools/report_470384_semicoherent_recovery.py`, `tools/report_d3_pilot_filter_prototypes.py`, `tools/replay_150802_pnt_kalman_v4_canary.py`, `tools/report_adaptive_dual_rx_phase.py`, the six September 25 phase report directories, and pure estimators under `src/leo/analysis/{qam,starlink,research}`. Existing scripts are references/adapters, not an instruction to rerun hard-coded historical captures. The direct-IQ report currently hard-codes 2.5 MS/s and 300,000-sample dwells and must be adapted before use here.

## 5. SOL execution packages and dependency gates

Do not launch workers as part of planning. At execution use SOL for the worker packages, with one coordinator and at most three workers concurrently. Keep separate output directories and ownership; no worker edits another worker's estimator or the sealed common input.

| Package | Owner scope | Prerequisite / handoff |
|---|---|---|
| A — Capture authority | Source/framing provenance, integrity, counter mapping, validity masks and coverage figure | Starts first; publishes versioned input manifest and audit. |
| B — Corrected acquisition | Pin GLRT runtime, tests, synthetic controls, legacy/corrected ablations, complete baseline acquisition and phase-blind associations | Code/test work can overlap A; real scoring waits for A's source policy. Publishes candidate and track inventory. |
| C — Experiment harness | Freeze cohort/splits, shared result schema, physical window schedules, cache interfaces and plot styles | Can prepare with A/B; seals actual units after A/B. Owns adapter tests and coverage accounting. |
| D — Frame and filter methods | Ledger 01–18, consuming shared frame observations; run filter families as checkpointed subtasks | A/B/C frozen. Writes `frame-methods/`. |
| E — Sync and bandwidth methods | Ledger 19–20, 25–26; native PSS/SSS, FFT and matched bandwidth | A/B/C frozen. Writes `sync-spectral/`. Coordinates shared FFT/direct parity contract with F through C. |
| F — Dual-RX local phase | Ledger 21–24; direct IQ, pilot products, double differences, trained responses | A/B/C frozen. Writes `dual-rx/`. Publishes phase observations with full reference conventions. |
| G — Cross-dwell and association | Ledger 27–30; consumes frozen associations and local observations; owns global-time boundary/geometry checks | A/B/C and relevant D–F outputs. Writes `cross-dwell/`. |
| H — Independent audit and report | Reconcile all 30 rows, holdout leakage, controls, denominators, code provenance, figures and limitations | Can inspect schemas early; final report waits for all packages, including explicit failures/unavailable cases. |

Each worker handoff must include exact input/output hashes, implementation revision, command/configuration, completed and pending units, exclusion reasons, measured CPU/I/O/RSS, component-owned test results, compact metrics and figures. Workers may not redefine shared cohorts, lower gates, or tune on evaluation outcomes. Proposed new variants go in a separately marked exploratory lane.

## 6. Lean execution and storage

- Offline saved-IQ work only. No radio commands, RF collection, deployment, production publication, QNAP modification, golden changes, or writes to the existing analysis namespace.
- Benchmark one metadata-selected visit per channel on development support, then an eight-visit smoke. Validate semantics before scaling. Cache compact frame/pilot observations once where numerical equivalence permits; cache keys include source hash, validity policy, geometry, absolute CFO branch, code hash and configuration.
- Start with one native-IQ reader and numerical-library threads limited to one per worker. Permit at most three compute workers after measuring memory and I/O. Avoid decompression of the same 21.25 GB independently for every report.
- Schedule checkpointed batches targeting 5–10 minutes each. Before expanding a method, report projected full cost from measured per-unit work. A costly full-population extension must not delay the 128-visit all-method comparison. Never disappear into a multi-hour batch; report progress and completed/eligible counts between batches.
- Runtime limits produce explicit incomplete rows and resumable checkpoints, not silent skips or scientific failures. Complete the ledger before declaring the study done. Historical hardware/PostgreSQL dependencies are replaced by already-frozen offline inputs when appropriate; any tests that genuinely require them use explicit markers.
- Keep report-local artifacts under `reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/`; use a dedicated local scratch directory for derived arrays. Use narrow data ports; analyzers consume arrays/contracts, not storage paths or private ORM models.

## 7. Final report and acceptance criteria

Deliver `REPORT.md`, `method-registry.json`, `source-provenance.json`, `selection.json`, per-unit observations, `method-summary.csv`, `exclusions.csv`, reproduction commands, test receipts, and standalone PNG/SVG figures. All figures must be regenerable from saved numerical outputs without reacquisition.

Required overview figures:

1. **Capture truth:** device-time coverage, target changes, invalid rows, payload gaps and all candidate adjacent boundaries.
2. **Effect of fixes:** legacy/corrected GLRT versus raw/RF-valid input, CFO search geometry and candidate changes, with acquisition losses and gains shown equally.
3. **All-method scorecard:** methods × coverage/held prediction/longest supported span/control separation/runtime. Separate panels for the different phase observables; unavailable and incomplete cells remain visible.
4. **Representative traces:** strongest, median and failing evaluation examples selected by a declared deterministic rule, labeled descriptive; same timestamps, scales and masks across compatible methods.
5. **Continuity ladder:** frame, 20 ms, 50–100 ms, full dwell, adjacent same-target boundary and retuned revisit, showing how much support survives each step.
6. **Spectral and bandwidth evidence:** direct/FFT parity, per-bin coherence and native/decimated paired outcomes.
7. **Cross-dwell evidence:** all qualifying boundary residuals, errors versus gap, joint-fit versus causal forecasts, and geometric signal size versus uncertainty.

The main table contains: approach; historical source report; exact variant; eligible/attempted/qualified/evaluation counts; held-out circular error with symmetry stated; R definition; maximum/median supported span; controls; runtime; outcome; figure link. Compare methods only on common observables/support. Report source timing uncertainty, clock/channel ambiguity, sample corruption and unresolved integer cycles as measured limits.

Completion means every ledger row is accounted for, capture/GLRT lineage is auditable, no conclusion depends solely on in-sample phase straightening or contaminated support, and all reported gains survive the appropriate held-out/control comparison. Local phase, modulo-π phase, RX-pair continuity, timing tracks and satellite geometry receive separate conclusions. If reliable geometric calibration or a usable two-signal population is absent, report that limitation with evidence while completing every feasible local method.
