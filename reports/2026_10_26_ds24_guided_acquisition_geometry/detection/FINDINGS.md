# Disjoint donor/confirmation findings

This is a synthetic-superposition mechanism prototype on eight inherited paired windows, both RX, CH1/4/7/8 and both pilot edges. It does not demonstrate natural pilot recovery, analog sensitivity, equal-FAR deployment, or localization improvement. No RF collection, GPS, production edit or raw IQ export occurred.

Each20ms/200000sample source window splits exactly into earlier[0,100000) and later[100000,200000),10ms/7.5frames each. Source-native half-open counters, generation, original IQ digest and separate overlay-support hashes are retained. No earlier samples or padding enter later scoring. Analytic pilot phase remains continuous across the split; only amplitude changes. Each injected strength is relative to that half's measured native background power, not physical antenna-input SNR.

First-rank guiding uses the first earlier blind candidate passing the original fractional0.025gate. It propagates timing by native counter delta and uses the measured earlier finalized CFO. All-proposal guiding independently evaluates every gatepassing donor, bounded8, and accepts on any pass. Truth never chooses either donor policy or enters their estimates; it only evaluates the fixed2sample/100Hz recovery criterion and supplies a separately labeled oracle lane.

| Earlier/later pilot ratio | Blind injected identity | Primary guided identity | All-proposal guided identity | Guided any pass (primary/all) | Oracle gate support |
|---|---:|---:|---:|---:|---:|
| zero_zero | N/A | N/A | N/A | 4/16 / 4/16 | 0/16 |
| weak_weak | 0/16 | 0/16 | 0/16 | 4/16 / 4/16 | 16/16 |
| strong_weak | 0/16 | 4/16 | 4/16 | 15/16 / 15/16 | 16/16 |
| strong_zero | N/A | N/A | N/A | 4/16 / 4/16 | 0/16 |

Ratios: weak=-24dB, strong=-18dB; zero means no injection. Weak/weak and strong/weak later samples are exactly identical, confirmed by support hashes. Strong/weak improves correctly finalized injected recovery from0/16 blind to4/16 guided, while oracle gate support is16/16. Wrong donors and no donors remain in the denominator: the strong earlier half gives11 correct injected first-rank donors,4 other detected donors,1 no donor. The all-proposal policy does not add recovery here.

Gate support is distinct from frequency measurement recovery. Of the11 correct earlier donors,7 pass later scoring but move to an adjacent residual-FFT bin, about±443.892Hz, failing the frozen100Hz CFO criterion. Donor timing stays propagated and donor CFO itself was within100Hz. The unchanged GLRT grid is FFT size512 over4.4microsecond symbol spacing. Even the supplied-truth oracle chooses a one-bin-wrong finalized CFO in9/16 weak later cells despite passing its gate in16/16. Prior round2 oracle figures were gate support only and must not be read as usable measurement recovery. No CFO estimator or tolerance was changed after these outcomes.

The4/16 guided gatepasses on strong/zero and zero/zero recorded backgrounds can be genuine pre-existing pilots. They are not false alarms. Donor ambiguity, the one donor acquisition failure, and later frequency precision are separate limits to this mechanism. A future donor-predictive CFO prior would need independent validation of real Doppler changes and uncertainty, rather than freezing frequency because synthetic truth is constant.

Null controls use genuine independent complex Gaussian later samples. The active bank has four earlier blind donor outputs, with1–3 gatepassing proposals each;64 independent later draws per bank produce256 independent confirmation RX trials. Each trial contributes one primary/all-proposal any-pass outcome, including every proposal in that policy. Separate noise-only earlier/later controls have64 independent RX trials.

| Null regime | N | Blind any-pass | Primary guide | All-proposal guide |
|---|---:|---:|---:|---:|
| active | 256 | 11 | 1 | 1 |
| noise | 64 | 4 | 0 | 0 |

The unchanged0.025gate on10ms blind searches is not calibrated to a rare false-alarm rate. These finite empirical rates do not establish equal FAR or operational improvement. Noise-only earlier halves produced no gatepassing donor, so their0/64 guided rate alone says little about confirmation with an active donor. The active bank supplies that needed conditional exposure. Bank donors are reused, but all later null vectors are independent and distinct.

Exact one-sided95%binomial upper bounds are reported for each fixed donor-bank/edge/RX stratum. Pooled bounds use a conservative independent-Bernoulli KL-Chernoff bound on average conditional FAR, allowing different probabilities across banks. They do not bound non-Gaussian recording backgrounds or extrapolate to an unseen donor population. See summary.json for every bound, stratum, paired outcome and per-RX/channel result. No rolled pilot is used as a null.

Process times: preflight7.16s, recorded60.99s, active null98.33s, independent two-half null43.08s. Every process had580second alarm and BLAS1. Full20ms historical parity passed on all8windows. Preflight both halves had exactly matching full candidates under the unchanged production port and explicit public10ms schedule, without replacement. All64 recorded scenario RXcells and all320 null RXtrials are retained; no failed physical slots.

Files: protocol.json and panel.json freeze sources and original authority; preflight.json verifies split feasibility/parity; recorded.json retains every donor/late candidate and native support; active_null.json/noise_null.json retain every null outcome and donor bank. cells.csv and summary.json provide lean comparisons. Four guiding tests validate blind ordering, truth-free inputs, source ownership and continuous analytic phase; two additional bound tests validate finite-trial calculations. verification.json and RF_seal.json bind outcomes and sources. Reproduction requires the exact historical PYTHONPATH and existing restricted recording access. No raw IQ is included.
