# Detection injection findings

All 8/8 paired windows completed with full unmodified historical candidate parity; 64/64 recorded injection RX-strength cells. Elapsed batch 79.1 seconds, BLAS1, 580-second alarm. Runtime identity unchanged: True.

Date/inventory selection: DS24-0010 and0011 in the existing 2026-10-24 analysis inventory; nearest full-scan midpoint per CH1/4/7/8, both RX. Lower and upper pilot edges are represented. No candidate outcome or GPS entered selection or inference.

| Pilot/background dB | Known-anchor pass /16 | Blind identity recovery /16 | Anchor pass, blind miss | Any blind gatepass /16 |
|---:|---:|---:|---:|---:|
| -24 | 16 | 0 | 16 | 4 |
| -18 | 16 | 16 | 0 | 16 |
| -12 | 16 | 16 | 0 | 16 |
| -6 | 16 | 16 | 0 | 16 |

The matched known anchor uses exactly the same complex64 injected samples as the complete blind search and the same 0.025 exact-minus-control gate. Identity recovery additionally requires timing within two native samples modulo exact 750-Hz repetition and finalized CFO within 100 Hz. Any gatepass can instead belong to a pre-existing pilot or an unrelated search candidate.

Anchor-supported blind misses identify acquisition/search loss for this injected flat-channel signal. Failure at the true anchor shows that this scoring lane does not admit the signal at that strength/background. This finite superposition experiment cannot assign natural CH7/8 yield differences to one cause across the corpus; high injection can mask or interfere with pre-existing signals. Measured reference power includes every signal, noise, DC, and interference component in the native recorded window. It is not physical antenna-input SNR.

Recorded zero-injection baseline: any gatepass in 4/16 RX cells. These are not false alarms because recordings may contain genuine pilots.

Every RX/channel has the same coarse-grid transition: known-anchor 2/2 and blind 0/2 at -24 dB, then both 2/2 at -18/-12/-6 dB. Thus matched flat-pilot injections expose acquisition/search sensitivity below the blind threshold, with no CH7/8-specific deficit resolved on this small panel and six-dB grid. Clean Gaussian controls show the same transition. This does not exclude weaker natural pilots, colored/interfering backgrounds, multipath, or a transition difference between tested strengths.

Injection occurs in native ADC samples after the RF chain, and strength is normalized separately to each RX-window background. It therefore cannot test antenna/LNB/front-end frequency-dependent gain or loss, or compare physical antenna-input detection thresholds. A natural CH7/8 signal can be weaker before this injection point while the digital detector responds identically to these matched ratios.

The one predeclared mechanism replay (last frozen slot, DS24-0011 CH8, both RX, -24 dB) reproduced saved injection exports exactly. Production searched 21 coarse CFO values times 13333 timing cells and retained eight nonmaximum-suppressed peaks. The best true-neighborhood local peak had coarse score 0.156400 / 0.155984, ranking 6808th / 7700th among 48367 / 48415 local peaks before suppression. Neither true neighborhood reached the original eight or diagnostic top256 coarse nominees; the eighth selected scores were 0.169560 / 0.170272. Thus these two misses occur at coarse acquisition retention, before fine CFO, candidate ordering, fractional timing or GLRT admission. The saved exports also have no final candidate within two samples of injected timing in all16 -24 dB cells, but only the two traced cells resolve the upstream mechanism.

The diagnostic extra256 proposal ranking never refined or admitted extra candidates. Exact-anchor scoring profiles the usual GLRT residual CFO at known timing/center; it bypasses coarse multiplicity and acquisition budget. Anchor success is not deployable blind recovery, independent detection validation, or equal-false-alarm-rate evidence. No threshold or whitening sweep was performed.

Clean controls use independent complex Gaussian noise across the two receivers, holding realizations across strengths and reusing them across edges. Noise-only produced 0/4 any gatepasses; the four RX-edge outcomes are only two underlying independent noise realizations, so false-alarm precision is weak. Wrong-sequence roll17 produced 0/4 passes at the original anchor but 4/4 blind gatepasses at approximately +748 native samples = 17 symbols. A rolled sequence is a retiming ambiguity for blind acquisition, not a clean null/FPR control. The worker constructs that wrong signal at -6 dB before calling evaluate with no additional injection; raw strength_db=None denotes no second overlay, and report.py labels its effective -6 dB strength explicitly. See summary.json for all strengths, cells.csv for per-RX/channel measurements and results.json for every exported candidate and parity check.

First-original-rank timing-matched gatepass CFO errors, one per RX-strength cell (no CFO-error selection): {'n': 48, 'median': 9.523043825989589, 'median_absolute': 9.523043825989589, 'maximum_absolute': 24.83606077040895}.

No position/localization claim, no production edit, no new RF collection, no raw IQ copied. Reader authority and IQ digests remain in panel/results receipts. The first metadata adapter failure and correction were preserved before IQ access; no visit was replaced.

Reproduce with the repository .venv Python and PYTHONPATH=/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src; set OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1. Metadata/IQ reads require the pre-existing privileged filesystem access (`sudo -n env ... study.py run`). Existing protocol.json must remain bound to original source hashes. `test_study.py` owns analytic-template, native-power, exact-period timing and noiseless known-anchor tests. Run `report.py` on results.json to regenerate CSV/figures.
