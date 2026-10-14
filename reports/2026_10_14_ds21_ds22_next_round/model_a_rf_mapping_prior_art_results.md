# A035/A053: RF mapping, shared calibration and satellite timing

The recorded RF labels are reproducible hypotheses; they are not measurements of the external LNB state. The new training-only derivative audit verifies the RF and timing directions in the actual native predictor, and finds substantial frequency-offset/timing confounding. It does not identify a hardware fault, select another RF mapping or justify promoting another RF coefficient. There were no new fits, reference joins, held scores or RF collections.

[Metadata and source hashes](model_a_rf_mapping_metadata.json) bind 32 actual recording metadata files, the two pinned TrackingInputs and inspected source code. [Complete diagnostic receipts and all candidate/block results](model_a_rf_mapping_prior_art_results.json) include the failed v1 and successful v2 attempts. Current states are the training-selected A035 fixed-55 union/locked-high winner and A053 fixed-59 union/locked-high/50 km winner, each in its own unchanged learned-contrast family. Their previously reported configured errors are 6.290 and 3.476 km; this audit does not reevaluate accuracy.

## What the actual recordings establish

| Case | Recording | Source windows | Segment manifests | Edge |
|---|---|---:|---:|---|
| 035 | `fast8-auto-20261012-092444-825e68b8-1-lower` | 6,763 | 14 | lower |
| 053 | `fast8-auto-20261012-135704-b4d3ffe7-1-upper` | 6,759 | 14 | upper |

All 28 manifests are complete. Within each recording, every segment has the same configuration and radio metadata, one serial `1040005e0b100007100010000bf33a5d4d`, receiver IDs `[0,1]`, interleaved sample/receiver/IQ layout and 2.5 MS/s rate. Their window totals match the pinned input provenance. The public fast-scan reports independently associate each recording name with its matching TrackingInput session/run. This metadata audit retains the raw recording authority digests but does not recompute them from every raw index/IQ byte.

Both recordings assign **9.75 GHz to CH1–4 and 10.6 GHz to CH5–8**, with `rf_mapping_authority="hypothesis"`. The actual RF export is **saved applied Pluto IF + saved LNB reference**. All 16 receiver/channel RF labels in each TrackingInput agree exactly with these sums. All requested and applied IF readbacks agree exactly.

| Channel | Assumed LNB, MHz | 035 applied IF, MHz | 035 labelled RF, MHz | 053 applied IF, MHz | 053 labelled RF, MHz |
|---:|---:|---:|---:|---:|---:|
| 1 | 9750 | 959.6875 | 10709.6875 | 1190.3125 | 10940.3125 |
| 2 | 9750 | 1209.6875 | 10959.6875 | 1440.3125 | 11190.3125 |
| 3 | 9750 | 1459.6875 | 11209.6875 | 1690.3125 | 11440.3125 |
| 4 | 9750 | 1709.6875 | 11459.6875 | 1940.3125 | 11690.3125 |
| 5 | 10600 | 1109.6875 | 11709.6875 | 1340.3125 | 11940.3125 |
| 6 | 10600 | 1359.6875 | 11959.6875 | 1590.3125 | 12190.3125 |
| 7 | 10600 | 1609.6875 | 12209.6875 | 1840.3125 | 12440.3125 |
| 8 | 10600 | 1859.6875 | 12459.6875 | 2090.3125 | 12690.3125 |

Every segment records `physical_lnb_control_changed=false`. The inspected qualified preparation writes/readbacks Pluto IF and explicitly says physical LNB LO is not switched or attested. This establishes the recorded control behavior. It does not establish whether an independently configured LNB was fixed, externally switched, shared between receivers, frequency locked, or accurately represented by either nominal reference.

Concrete missing authorities are the recording-bound LNB make/model and per-receiver topology; physical LO frequency, band/polarization state and lock history; measured reference/sample-rate error; and independent absolute carrier/identity evidence. No current metadata answers these facts. A hardware answer must not be inferred from successful numerical closure or a better conditional score.

## The fitted coefficient is not the physical Doppler scale

The original design has separate receiver intercepts/drifts and one shared additive column `(RF−RF_center)/1e9`. Its coefficient `c` has units Hz/GHz. Clock functions and the path's fixed two-receiver high-band contrast are additional correction terms. The physical speed of light remains fixed.

The native predictor already computes orbital Doppler as `D = −RF × radial_velocity / LIGHT_KM_S`. Consequently an RF-label offset has orbital derivative `D/RF`, which varies with candidate, time and geography. The additive fitted-`c` direction is candidate independent. A wrong absolute carrier label therefore need not be absorbed by fitted `c`. Changing labels also changes the additive RF function unless its frame is explicitly transported: at fixed center/baseline, its direct contribution is `c × ΔRF/1e9`. The audit records this separately, −0.610058/−0.692619 Hz per MHz for 035/053. It does not silently recenter calibration or the saved baseline.

AD9361 documentation describes two receive channels sharing a frequency synthesizer and a common clock-reference architecture. That makes a common instrumental frequency term physically plausible within that chip, but it does not attest these recordings' external LNB oscillators or equate empirical fitted `c` with measured hardware ppm. [AD9361 Rev. G, theory of operation](https://www.analog.com/media/en/technical-documentation/data-sheets/AD9361.pdf).

Transmitter frequency behavior is a separate hypothesis. Primary Starlink measurements distinguish carrier, frame and symbol clocks; frame timing corrections cannot simply be treated as carrier-frequency calibration. Their reported carrier behavior motivates testing frequency directions but supplies no calibrated correction for our recordings. [Morrison et al., real-time Starlink SDR measurements](https://radionavlab.ae.utexas.edu/wp-content/uploads/morrison_rtsdr_LEOPNT_2.pdf).

## Relevant earlier controls

These are separate algorithm versions/data sets; their scores are not compared with current 035/053 scores.

| Existing control | Matched frequency/score result | Position result |
|---|---|---|
| DS21-039 receiver contrast `c+d / c−d`, four 20 s/600-iteration calls, all strict | Objective −0.656914 | 4.072515 → 4.085344 km, worse |
| DS21-039 compatible band/time/RF calibration, four strict calls | Training NLL −17.222004; held NLL −2.949026 | 4.072515 → 4.186817 km, worse |
| Consumed DS16/17/18 development cohort, 148 cases: dynamic RF-time versus matched RF-off refit | Receiver-specific RF×time terms | Mean error −0.007900 km; 87 improved/60 regressed/1 tied |
| Same old cohort: satellite slope σ=0.5 Hz/s versus RF refit | Adds regularized satellite slope terms | Mean error −0.082542 km; 100 improved/48 regressed |

See the [receiver contrast result](../2026_10_13_ds21_039_root_cause/RX_RF_CONTRAST_RESULTS.md), [native band result](../2026_10_13_ds21_039_association/NATIVE_BAND_CALIBRATION_RESULTS.md), and historical `reports/2026_10_09_position_error_iter85/CONTROLLED_EFFECTS.md` (tracked Git report, possibly outside sparse checkout). These establish that model flexibility and lower frequency loss alone have not reliably corrected localization. No new zero-`c` experiment was run; the session's fitted-`c` scope is retained.

`hard60_dynamic_rf.py` already implements two receiver-specific `(RF−center)×(time−center)` columns. `hard60_satellite_correction.py` already implements zero-sum satellite additive offsets (σ=50 Hz) and/or time slopes, while retaining orbital timing freedom. The production B7 chain uses **slope only**, with σ=0.5 Hz/s; the existence of the offset implementation is not evidence that an offset-only current-DS21 control has already succeeded or failed. Satellite offsets/slopes are empirical corrections, not a measured ephemeris or transmitter clock.

There is also a directly relevant discrete-LO sensitivity in the [fast-channel root-cause report](../2026_10_12_fast_channel_root_cause/README.md). On another saved capture and frozen satellite candidates, recorded split references gave fitted-`c` held RMS **102.7 Hz**; both-fixed-9.75 **3248.9 Hz**; both-fixed-10.6 **3570.4 Hz**; the two opposite receiver-specific fixed assignments **3297.0/3523.5 Hz**. Those alternatives were conditionally poor. They were **not fresh full association searches**, cannot establish the physical LO, and do not resolve 035/053. No new held test is performed here.

## Native derivative and conditioning qualification

Source `eaf2074dd` introduced the diagnostic; source `9cf0977aa` is the successful frozen v2. Six original tests plus two v2 tests pass, including actual native orbit/likelihood evaluation, public two-case serialization, rank degeneracy, unsupported timing-FD rejection and subnormal-posterior handling. Ruff passes.

V2 uses two original objective replays and 18 explicit native predictions, plus the two predictors internal to those objective replays. It completed in **4.281 s** (outer wave142 **8.034 s**), within 120/135/140 seconds internal/TERM/KILL. There are zero optimizer/reference/held calls. All original observations, candidate banks, priors, selected states, group shifts, clock functions and RF centers remain unchanged.

| Certificate | 035 | 053 |
|---|---:|---:|
| Maximum RF derivative error, Hz/Hz, native ±1 MHz | 4.442e−17 | 4.455e−17 |
| Maximum smooth timing derivative error, Hz/s, native ±0.0001 s | 3.423e−6 | 3.359e−6 |
| Interpolation-seam pairs excluded from smooth timing certificate | 141 | 79 |
| RF/timing visibility-change pairs | 0 | 0 |
| Invisible pairs explicitly counted | 175 | 779 |
| Positive-posterior pairs | 9,250 | 5,269 |
| Common/clock/geography design rank | 27/27 | 27/27 |
| Design including all satellite timing directions | 82/82 | 86/86 |

Invisible candidates are not used as positive signal support. Predictions remain reported/certified algebraically on invisible pairs, while likelihood conditioning uses only positive posterior support. Zero posterior rows make exactly zero contribution and are counted separately. V1 stopped before publication of a result because two positive subnormal probabilities produced zero curvature when divided by σ². Its failed namespace/wave141 is retained. V2 retains those two rows and reports their **4.887e−320** total mass with zero curvature; no observations are removed. V1 used one objective/nine explicit predictor calls; combined actual totals are **three objective/27 explicit predictor calls, zero fits**. No frozen source or failed receipt was repaired.

The diagnostic weights are fixed posterior signal probability divided by σ². It removes the normalized SVD span of original receiver lines/shared `c`/common-clock functions, two diagnostic receiver/group intercepts, geography, then all satellite timing derivatives. The group intercepts are included as a permissive confounding control although the final A contrast is fixed. Priors and active parameter constraints are deliberately absent from this *descriptive* conditioning; it is not a feasible optimization tangent, covariance, calibrated information matrix, uncertainty interval or fitted profile.

## What remains after conditioning

Positive log-score means an infinitesimal increase in that named direction improves the training likelihood. RF-mapping directions use MHz; receiver contrast uses Hz/GHz. The following are exact first-order arithmetic at the saved states, not new parameter estimates.

| Direction | 035 conditioned log-score | 053 conditioned log-score | Positive/negative 20 s blocks, 035 | Positive/negative blocks, 053 |
|---|---:|---:|---:|---:|
| Common orbital RF mapping offset | +1.597928 | −0.629484 | 9/6 | 4/9 |
| CH1–4 mapping offset | −2.721849 | −0.784947 | 4/11 | 8/5 |
| CH5–8 mapping offset | +4.319777 | +0.155462 | 9/6 | 6/7 |
| Receiver RF contrast | −0.085463 | +0.027332 | 5/10 | 9/4 |

The mapping directions retain 24–35% of their original weighted norm after conditioning, so they are not algebraically identical to shared `c`, clocks or timing. Shared-`c` raw scores are nearly zero (−7.02e−8/−1.52e−7), while receiver contributions oppose; pooled stationarity does not imply every omitted RF contrast is zero. However case/block signs differ, and 053's high-group mapping score changes from raw **−1.722087** to conditioned **+0.155462**. This is direct evidence of confounding, not a stable hardware calibration estimate.

All 55/59 candidate records and every supported training block are retained. After conditioning on common calibration/clock/geography, the signal-mass-weighted median absolute cosine between a candidate's additive constant-frequency direction and its own orbital timing direction is **0.972986 / 0.956023**. For an RF-proportional additive direction it is **0.977732 / 0.957306**. The receipt also retains physical emitted-frequency first-order directions `1+D/RF` and `(RF+D)/1e9`, separately from received additive constant/RF terms. Their definitions avoid silently identifying a received additive offset with a transmitter oscillator.

These strong local alignments make it plausible that free orbital shifts absorb carrier-frequency structure over a short capture. The same alignment makes the two explanations difficult to identify from these assignments. It does not establish that fitted timing is physically erroneous, that every candidate identity is correct, or that frequency parameters improve geography. Along-track ephemeris error can induce a timing-like state perturbation; transmitter/receiver biases can produce similar frequency residuals without such an orbit error.

## Next falsifiable check

The infinitesimal audit does **not** test the finite ±850 MHz changes implied by fixed-LO alternatives. A useful next training-only qualification can retain the exact existing 55/59 bank, physical states, own disk, observation/CFO inventory and priors, and evaluate three explicitly named mappings: recorded split reference; all 9.75 GHz; all 10.6 GHz. Derive every RF from the saved actual IF plus the hypothesized LO, rather than channel labels alone. Rebuild or explicitly transport the RF-center/design frame and preserve the existing additive calibration function at zero change; bind the two distinct effects of orbital RF scaling and additive RF-function relabelling. The identity mapping must reproduce objective, complete gradients, responsibilities and correction function before finite alternatives are interpreted.

At finite alternatives, report loss and assignment/support changes for all mappings/states without truth or held selection. Frozen-bank scores are conditional sensitivity only: a large RF-label change can invalidate a bank discovered under the original labels, and poor fixed-bank loss cannot reject the physical LO hypothesis. A successful closure also cannot attest that LO. No fits or discrete mapping experiment are launched by this report. A recording-bound hardware answer would determine which finite mappings deserve subsequent association-aware testing; meanwhile the existing hypotheses remain explicitly unconfirmed.

A concrete function-preserving transport is available for qualification. If the two groups change by Δlow/Δhigh and the native RF center changes from f0 to f0′, retain `c` and set `a′_r = a_r + c×[(f0′−f0)−Δlow]/1e9` and `h′_r = h_r − c×(Δhigh−Δlow)/1e9`. Keep receiver drift, clocks, baseline, geography and satellite timings exactly. This reproduces the original additive correction pointwise, while the orbital predictor sees the finite new RF labels. Alias/coefficient bounds must be checked without projection or branch repair. Both fixed-LO alternatives have the same centered RF design here, but distinct absolute orbital RF. An eight-objective/six-explicit-predictor, zero-fit qualification (source plus three rebuilt mappings per case) would first require the identity transport to reproduce objective, complete gradients and responsibilities; it would not rank mappings by reference or extrapolate infinitesimal derivatives across 850 MHz.
