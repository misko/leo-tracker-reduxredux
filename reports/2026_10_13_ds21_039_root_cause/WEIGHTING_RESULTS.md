# DS21-039: three matched observation-weight controls

**None of the three weighting controls improved position accuracy over the matched unweighted continuation. None reached <0.5 km, and none is promoted.** Every scheme selected its `free-cold-high` start using its own training objective; root evaluated position only after the outcomes and selections were sealed.

| Prespecified scheme | Post-seal error, km | Change from matched unweighted error |
| --- | ---: | ---: |
| Matched unweighted free continuation, reused | 4.072514870 | — |
| Equal band | 4.313586908 | +0.241072038 |
| Equal acquisition block | 4.106033136 | +0.033518266 |
| Equal band, then block within band | 4.591629789 | +0.519114919 |

Each nonuniform scheme used exactly the four physical initializers of the previous free-geography experiment: the original all-band winner and the three sealed cold-profile winners. Each call had the same original all-band inputs, 43-satellite bank, native candidates/times, RF/time/group frame, fitted-c parameters, priors, original start-5 center, 25-km disk and 20-second/600-iteration allowance. The four unweighted baseline calls were reused, not rerun. A historical incumbent was not presumed stationary under new weights and was not automatically eligible for weighted selection.

Weights were fixed from training metadata before fitting. There were 2,798 original windows: 1,692 low-band and 1,106 high-band windows, across 12 observed training blocks. Blocks use **`floor(original observation center times_s / 20)`**, matching the preceding diagnostic. Labels remain `0,1,3,4,5,7,8,9,10,11,13,14`; gaps were not compressed. Group fractions and both centering frames stayed original.

| Scheme | Fixed mass allocation | Minimum window weight | Maximum window weight | Total window weight |
| --- | --- | ---: | ---: | ---: |
| Equal band | N/2 to each available band | 0.826832151 | 1.264918626 | 2798 |
| Equal acquisition block | N/12 to each available block | 0.742569002 | 1.475738397 | 2798 |
| Equal band, then block | N/2 per band, divided equally over that band's available blocks | 0.616843034 | 1.975988701 | 2798 |

Weights sum to N within floating precision; their independently reconstructed formula differs by at most 2.23e−16 per window. Timing and calibration priors are added once, with unchanged strengths. The source mixture's conditional posterior probabilities remain unchanged at a fixed parameter state; only likelihood contributions and gradients are weighted. This is a **composite training objective**, not a newly normalized predictive density. Weighted objective values across different schemes cannot be ranked as scores of one common likelihood.

Before any optimizer call, a unit-weight model replayed all four original parent states. Saved parent objective/NLL deltas were exactly zero. Unit-model scalar differences were at most 3.64e−11; both physical-vector and nuisance gradients matched exactly. All 327 live scientific sources, archived snapshots and input/ancestor hashes matched their freeze.

All **12/12** new fits were stationary and interior; there were no budget failures, retries, substituted starts or fallback winners. Selected KKT statistics were 0.000085813, 0.000326620 and 0.000051257. Every attempted outcome, including the other three starts per scheme, remains in the terminal and individual receipts. The fit phase took 131.367 seconds, with 130.638 seconds summed reported optimizer time, within its 240-second aggregate optimizer allowance. Root's coordinator time including preparation was 155.619 seconds, within the 350-second external bound.

| Selected state | Own weighted objective | Weighted likelihood NLL | Unweighted likelihood NLL | Prior cost, once | Common unweighted objective | Unweighted native RMS, Hz |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Matched unweighted continuation | 32380.954535 | 32225.181022 | 32225.181022 | 155.773513 | 32380.954535 | 92.162359 |
| Equal band | 32280.004923 | 32123.985606 | 32228.598109 | 156.019317 | 32384.617426 | 94.419686 |
| Equal acquisition block | 32359.629002 | 32203.809824 | 32226.916483 | 155.819179 | 32382.735662 | 92.026181 |
| Equal band, then block | 32336.098960 | 32180.035983 | 32232.116742 | 156.062977 | 32388.179719 | 94.539749 |

The common unweighted objective is the same original likelihood plus the unchanged prior at each selected state. It worsened by 3.662891, 1.781127 and 7.225185, respectively. Equal-block native RMS decreased slightly while position error increased; residual fit alone does not establish localization improvement. Weighted native RMS values were 92.887503, 91.578219 and 92.327607 Hz, each conditional on its signal assignments and weighting convention.

Independent receipt-only audits confirmed the minimum-stationary selector, all 12 launch/termination/outcome bindings, unchanged disk support, and weighted/unweighted band and shared-prior ledgers. Selected fit objective and weighted NLL replay their diagnostics; maximum ledger closure error is 3.64e−12. See the separate [weighting ledger audit](WEIGHTING_LEDGER_AUDIT.json) for component-level prior reconstruction. No predictor or optimizer was run during these audits.

These negative controls test **coverage/count imbalance while preserving sum of weights N**. They do **not** test effective independent information, correlated measurement-noise covariance, or the overall likelihood-to-prior scale. They do not rule out correlation. Block mean residual structure may arise from model misspecification, association changes or correlation; it is not evidence of a physical clock defect by itself. The experiment also does not establish a global optimum or resolve the earlier optimization-path sensitivity.

Root's retained local post-seal evaluation, `local/weighting-v1/development-errors.json`, supplies the three position errors, using the configured station location rather than an independently surveyed reference. Its terminal/protocol bindings were verified. No reference information or held observations entered these controls or selection.

Evidence retained locally under `local/weighting-v1/`: `fits/terminal.json`, `fits/weights.json`, `fits/unit-replay.json`, and `freeze.json`; see also the [matched baseline report](REFINEMENT_RESULTS.md). Runner `0adc3c2ec` and component `fb1d7c67f` passed 42 combined focused tests; Ruff and independent source review were clear. The DS21-039 optimization controls now total **18 cold + 7 refinement + 12 weighting = 37 new fitted-c calls**; no extra unweighted calls were added for this comparison.

| Sealed artifact | SHA-256 |
| --- | --- |
| Weighting terminal | `e288a3306f5669c81de2a634c85bb1402559cf8445966bb16237d0109dad08c5` |
| Weighting freeze | `f2e41e22138036e2a42395e650434f8fd5181df70c560f227ebdef7f9bdf7464` |
| Weight inventory | `71ff2e910f7f6f39e75c918d53e3415080575f8f755eb23adb75dac60b456d69` |
| Unit replay | `dee0dde0e7181618ad246d2844c630ab8fccf9f6e41b0bbfb4b532452453ac96` |
| Root post-seal position evaluation | `4453aa6a120c30b014ab2ced3f4b81bba6e807a58f6aa209b5cf3650195646a0` |
