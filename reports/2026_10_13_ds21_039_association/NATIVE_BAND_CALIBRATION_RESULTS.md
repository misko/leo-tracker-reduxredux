# DS21-039: compatible band calibration improves frequency fit, worsens localization

The prespecified native band-calibration control is **negative for localization**. The training-selected compatible model lowers held NLL by **2.949** on identical held support, but its development position error rises from **4.072515 to 4.186817 km**, a **114.3 m worsening**. Neither result reaches 0.5 km. The expanded model is not promoted. The held difference is descriptive; it establishes neither statistical significance nor better position accuracy.

The [protocol](NATIVE_BAND_CALIBRATION_PROTOCOL.md) tests the specific representational limitation found by the [capacity diagnostic](BAND_FUNCTION_CAPACITY_RESULTS.md): two receiver band×native-time drift contrasts and one common band×RF contrast. It preserves fitted `c`, the original 43-satellite bank, all 2,798 training windows / 3,714 native candidates, singleton marginalized satellite/native/clutter likelihood, original physical/group priors, seed-5 25 km local disk and two saved original/refined starts. Added drift uses exact candidate timestamps. Training time/RF centers and receiver/global high fractions are retained for held prediction. No additional Gaussian priors, reference-derived seeds or held selection enter the control.

## All four prescribed fits

Every fit returned stationary and feasible; no failure, retry or nonstationary result was discarded. Compatible stationarity uses one coupled KKT audit over all 55 scaled parameters, including shared and effective per-band coefficient limits, timing and geographic constraints. Original fits retain their original audit. All boundary flags are false.

| Model / source start | Training objective | Training NLL | Scaled KKT | Fit seconds |
| --- | ---: | ---: | ---: | ---: |
| Original / original-all | 33172.423429 | 32969.499770 | 0.000536 | 0.591 |
| Original / refinement-free | 32380.954535 | 32225.181022 | 0.000070 | 0.799 |
| Compatible / original-all | 33164.778079 | 32961.548361 | 0.000285 | 6.939 |
| Compatible / refinement-free | 32363.806373 | 32207.959018 | 0.000466 | 7.376 |

Original selection retains `incumbent-refinement-free`: its objective equals the new original/refined result, and the prescribed name tie-break retains the incumbent. Compatible selection is the newly fitted `compatible-refinement-free`; zero-tail source incumbents are ineligible for that condition. Both selections are own-model training argmins, sealed before held preparation. The added function-space rank is **5 → 8**, with three independent dimensions. Both zero-tail source oracles reproduce objective, NLL, all original gradients, satellite/clutter posteriors and saved source scalars **exactly**.

## Selected corrections and held prediction

The compatible winner has drift contrasts `q_RX0=0.247750`, `q_RX1=0.611072 Hz/s` and RF contrast `d=−24.200680 Hz/GHz`. Its shared fitted `c` is **−606.803435 Hz/GHz**, versus **−618.997814** in the original winner. Effective coefficients are:

| Physical coefficient | Low band | High band |
| --- | ---: | ---: |
| RX0 drift, Hz/s | 3.168498 | 3.416248 |
| RX1 drift, Hz/s | 2.467978 | 3.079049 |
| Common RF slope, Hz/GHz | −597.237333 | −621.438014 |

Shared and effective drift/RF boxes remain ±60 Hz/s / ±5000 Hz/GHz; extra safety boxes remain ±120 / ±10000. The winner has no active inequality or coefficient box. Its smallest physical/coupled inequality slack is **3.811805**, from a satellite timing constraint; total satellite shifts span **−16.188195 to +15.904338 s**. The relative timing prior remains substantial: **155.243574 → 155.321152** objective units. Adding band compatibility does not remove that timing adjustment, and these receipts do not establish that the timing adjustment is physically wrong.

| Selected-condition metric | Original | Compatible | Compatible − original |
| --- | ---: | ---: | ---: |
| Training objective | 32380.954535 | 32363.806373 | −17.148162 |
| Training NLL | 32225.181022 | 32207.959018 | −17.222004 |
| Held NLL | 7305.961858 | 7303.012832 | −2.949026 |
| Development error, km | 4.072515 | 4.186817 | +0.114302 |

Both held predictions use the same **633 windows / 849 native candidates**, with zero training-window overlap, zero measured waveform candidates and zero temporal edges. Each condition makes one native prediction and no held fit. Per-window NLL sums and original marginalized NLL agree exactly; satellite/clutter closure errors remain below 9e−16. Held signal/clutter masses are **492.452 / 140.548** and **492.202 / 140.798**, closing to 633. The NLL reduction is approximately **0.004659 per held window**. The historical training RMS of posterior-mean residuals falls **92.149562 → 90.920715 Hz**; this is not the RMS across all native residual branches or a position-accuracy measure.

Original six-start, seed-5 selected view baselines remain **4.291227 km all / 3.758515 km low / 2.556792 km high**. The half-band fits inherit all-channel training initialization; they are not independent band-only pipelines. Their view conditions differ from this matched all-band control. The compatible all-band result still exceeds both half-band errors. The configured development reference is not independently surveyed ground truth.

## Receipt audit and implication

Independent metadata-only audit checked **345 live/archive source pairs**, the unchanged original **339-source** subset, ancestor archives and 61 nested input/receipt bindings; exact source starts; four launch/result/termination identities; all training/final/outer seals; training argmins; original prior ledgers; and every compatible physical/band inequality. Reconstructed slacks differ from saved values by at most **7.11e−15**, and prior-ledger closure by **4.01e−12**. Recorded full KKT evidence is source-bound; the audit makes no new gradient evaluation or KKT solve. Held support is identical, and the evaluation binds the completed terminal/seal and was written afterward. [Compact audit and hashes](NATIVE_BAND_CALIBRATION_AUDIT.json) retain all four outcomes and coefficient summaries.

The entire slice took **42.228 seconds**, inside the prescribed **165 / 175 / 180 seconds internal / TERM / KILL** and four **20-second / 600-iteration** fit caps. Numerical sources remain frozen. This result supports empirical band-function flexibility for frequency fit, while rejecting its promotion as a DS21-039 localization correction. It does not identify transmitter hardware or rule out other missing physics. The next retained direction is the planned timing/calibration factorial and assignment attribution at saved fixed-position states, with no new position fits or timing-prior tuning.
