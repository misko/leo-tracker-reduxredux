# Joint constant-band contrast: blocked interpolation pilot

The fitted-c TRAIN-profile plus joint-band policy improves held coverage from 788 to 815/1909 and requested held coverage from 68 to 70/80 versus matched frozen-band continuation. Held NLL changes by -209.07. This is a single previously selected source, not completion of the 15-window goal.

| Policy | c arm | Train / 2073 | Held / 1909 | Requested held / 80 | Held NLL | Calls | KKT |
|---|---|---:|---:|---:|---:|---:|---:|
| frozen | fitted-c | 1088 | 788 | 68 | 23226.28 | 287 | 6.53e-05 |
| frozen | zero-c | 829 | 478 | 37 | 24809.20 | 431 | 0.000183 |
| free | fitted-c | 1127 | 815 | 70 | 23017.21 | 503 | 8.31e-05 |
| free | zero-c | 1038 | 722 | 51 | 23626.03 | 599 | 0.000969 |

Fitted-c held gains are 84 and losses 57, leaving 731 retained. On that intersection, frequency RMS changes 173.13 to 162.35 Hz. Overall associated RMS changes 176.62 to 168.31 Hz; the selected sets differ.

Held NLL improves in 5/7 blocks. The strongest block (260–280 s) contributes -100.53; the other blocks sum to -108.53. The preceding fixed-state profile gain was concentrated in the 260–280 s block, so this follow-up also reports every held block rather than treating an aggregate gain as broad transfer.

The three requested held windows change 007:21→21/26 (one gain, one loss), 008:21→24/28 (three gains), and 009:26→25/26 (one loss). Thus windows at ≥80% change 2→3/3, with net requested gain two. These 80 points occupy only two held time blocks. All 693 requested points remain accounted as 58 train,80 held,0 boundary and555 other-source points untested. All20084 context points remain2073 train,1909 held,6 boundary and16096 other-source points untested. No untested point is counted as recovered.

Both arms use the original fixed TRAIN-discovered bank of45 candidates and native0–300s learned clock. Membership uses whole probes in deterministic alternating20s counter blocks, excluding straddlers; the clock interpolates across gaps. No held CFO, gate or score enters selection, discovery, seeds or calibration. All four endpoints and then their metadata-only predictions were frozen before held scoring. The classifier remains best satellite posterior > clutter at the original125Hz width. Labels are model associations, not confirmed emitter identities.

The free model retains all physical, timing, clock and q parameters, original q budget and all priors. Only receiver high-band constants become free, bounded by the original absolute alias limits with5000Hz scales. The frozen absolute contrast prior is replaced by the variable absolute50000Hz prior exactly once. A research subclass preserves exact singleton original objective and all existing gradients at the original contrasts, including the q/visibility normalizer terms. Seven component tests pass; actual training objective/gradient nesting, exact correction transport, CFO-invariant predictions and all four strict endpoints are independently replayed in verification.json.

Each policy has1000 objective/density calls and120s maximum. The free policy charges the sealed159-call TRAIN-only profile plus2 real seed qualifications, leaving839 calls for joint refit; fittedc uses342 andc0 uses438, totaling503/599. Original incumbents remain eligible. Frozen control endpoints are exactly reused after all pinned source files, identical terminal seeds, all-2s wrapper semantics, bank/mask/prior and endpoint objectives/gradients are qualified:287/431 calls. Reuse and independent replay costs are separate from optimization in results.json and verification.json. This compares profile+joint policy with frozen continuation, not a pure causal effect of adding two parameters.

Both continuations use common.refit’s broad regional disk. The extra25km disk from original production is not imposed. This is explicitly a matched research continuation domain, not an unchanged production-policy comparison. Original TRAIN discovery used fittedc; c0 sets only physicalvector[6]=0 at the common terminal seed and fixes it during continuation. It is conditional downstream sensitivity, not whole-pipelinec0. Better frequency fit alone establishes no location-accuracy improvement.

Position diagnostics use the matching configured reference only after prediction freeze; it is operator-supplied and survey uncertainty is unknown. The physical vector begins with east/north kilometers, not latitude/longitude; the raw results field position_vector_deg was misnamed. position-diagnostic.json decodes public coordinates and records each endpoint’s distance from the original shape-all production center and whether it lies within the original25km disk.

| Policy | c arm | Configured distance km | Movement from terminal km | Old center distance km | Within old25km |
|---|---|---:|---:|---:|---|
| frozen | fitted-c | 7.346 | 1.749 | 26.747 | False |
| frozen | zero-c | 11.698 | 6.942 | 21.018 | True |
| free | fitted-c | 7.481 | 1.562 | 26.559 | False |
| free | zero-c | 9.998 | 2.026 | 23.120 | True |

Donor contrasts were frozen before final geometry/timing/clock/q optimization. A shifted coupled optimum can motivate joint constants. The conditional-density normalizer is not itself evidence of an old frequency-gradient bug: at identical predictions, hard visibility and uniformq, legacy and shared frequency gradients agree. This pilot does not identify a unique cause. No drift term, expanded bank, special satellite/window seed or station-coordinate initialization was added.

Fitted-c absolute contrasts (Hz): frozen[-15031.27,34766.82], free[-15379.91,37631.22], updates[-348.64,+2864.40]. Conditionalc0 free updates[-1432.73,+2387.49]. All4 endpoints pass the unchanged≤0.001 KKT threshold; c0 free is close at0.000969. No relaxed tolerance or extra cleanup run was used.

![Paired held blocks and same-count timing histograms](paired-blocks-and-timing.png)

Files: protocol.json binds prefit policy/hashes; control-reuse-qualification.json and qualification-*.json bind exact seeds; endpoint-freeze.json and prediction-freeze.json establish evaluation order; fit-*.json/predictions-*.npz/evaluation-*.npz retain endpoints and measurements; held-blocks.csv and window-comparison.csv retain losses and denominators. No additional fits were launched for this report.
