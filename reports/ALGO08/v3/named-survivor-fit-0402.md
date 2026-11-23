# The named final fit reproduces the DS30-0402 positions on the fast roster

Running named v3's original five-refresh numerical fit on the fast solver's accepted roster reduced the remaining position displacement from **20.33 / 19.39 m** to **0.050 / 0.013 mm**, for fixed zero and fitted c respectively. Both arms preserved all **4,821 ordered observation, NORAD and role rows**. The complete saved publication took **29.440 s** through exit. The earlier warm fit took **24.082 s** and the archived named v3 publication took **73.351 s**. [Frozen protocol](final-fit-0402-protocol.md) · [Sealed measurements](measurements/named-survivor-fit-0402.json.gz)

| Saved route | Horizontal error, fixed zero / fitted c | RF RMS, fixed zero / fitted c | Through-exit wall |
| --- | ---: | ---: | ---: |
| Archived named v3 | 0.863650648 / 0.860301627 km | 100.672203444 / 100.576460190 Hz | 73.351 s |
| Earlier fast roster with warm fit | 0.883846703 / 0.879494951 km | 100.675328224 / 100.578974081 Hz | 24.082 s |
| Fast roster with original named final fit | 0.863650693 / 0.860301640 km | 100.672203450 / 100.576460192 Hz | 29.440 s |

The scoped option leaves discovery, isolated salvage, predictive nomination and the shared endpoint repair intact. It recomputes the original signed-history qualification from the live causal inputs. Once qualified, it uses the original signed means, exact same roster and released `event_position.refit`, starting each arm at the offered center with zero phase. Both original paired gates pass. The original ordinary paired fit remains the fallback if qualification or the final pair fails. No survey, named terminal or recorded owner list enters the algorithm. [Reusable opt-in](named_survivor_fit.py) · [Earlier combined route](isolated-salvage-0402.md)

## Which numerical inputs differ

The original named pre-cavity stage, captured separately after the new publication exited, verifies rank 1, both exact named endpoints and RF RMS, all 4,821 ordered rows per arm and zero objective replay discrepancy. Its original archived cavity stage adopted no replacement. The separate capture ran no grid, plots or standard publication.

All 85 active curved fragments and all 39 predictive fragments agree in original observations, signed aliases, clock, CFO and RF. The curved family powers, per-point noise and hardware/smooth design fingerprints agree exactly. Predictive covariance inputs and its cross-receiver support flags agree. The same 24 families own observations, and their causal means, phase widths, sky and physical modes agree. The same 22 families have orbital modes. Active posterior phase differences after the two cold fits are at most **8.22 / 3.45 ns**. The earlier warm option had accepted two phase refreshes. Both cold runs reached their terminal sites at refresh three and retained them through refresh five. Changing the full numerical schedule resolves the earlier displacement. This experiment does not isolate the effects of the different start, refresh count and termination criteria from one another.

Four zero-row nominal curve assignments differ. They yield 35 phase coordinates on the fast roster versus 34 on named v3, with differences confined to dormant families. The extra unsupported coordinate adds the released Student ν = 3 prior gap of **0.314628922645**. Subtracting that value from the observed objective difference leaves **2.32 × 10⁻⁹ / −1.69 × 10⁻¹¹**. All 179 grid calls align within 0.050 mm. After removing the same constant, maximum grid score differences are **1.73 × 10⁻⁶ / 1.05 × 10⁻⁶**. [Released unused-coordinate normalization](../../../src/leo/analysis/localization_v3/cavity_prediction.py)

## What the fit costs

| Saved scope | Earlier warm finish CPU | Original named finish CPU |
| --- | ---: | ---: |
| Candidate inference before signed conditioning | 10.119 s | 10.189 s |
| Complete signed stage | 0.574 s | 2.484 s |
| Standard numerical evidence | 5.155 s | 5.373 s |
| Full numerical solve | 20.791 s | 26.065 s |
| Complete publication through exit | 24.060 s | 29.427 s |

The two new final fits cost **1.287 and 1.137 CPU s**. Signed qualification and prior preparation cost 0.052 s. Collecting the witness cost 0.008 s, and writing it cost another 0.008 s. The directly measured signed-stage premium is **1.910 CPU s**. The complete saved run was **5.358 s** slower than the earlier warm run. These were separate runs, and the three measured inference intervals explain only part of that difference. The remaining numerical latency is outside their measured boundaries. Both candidates consumed the same staged inputs with zero filesystem input blocks. The separate named pre-cavity diagnostic took **32.178 s** and is excluded from the candidate clock. The ratio to archived named v3 is **2.49×** on this saved case, with earlier named input blocks and different runs. This does not measure raw acquisition or independent location transfer.

Both sidecars bind the candidate's actual position PNG. It publishes a complete 179-point grid and all eight verified PNGs. All four orbit legends match the 24 fitted satellite labels and the unassociated label, with a minimum 26 px gap. Figure dimensions match both comparators. All eight encoded and decoded digests differ from each comparator. Sixteen focused and adjacent tests passed.

Use `named_survivor_0402_trial.py launch NEW_TMPFS_ROOT`, followed by `evaluate NEW_TMPFS_ROOT RECEIPT`, with the installed named interpreter, source paths and shared low-priority CPU 2 wrapper. The driver records each child clock before validating any output. The reusable option wraps the already enabled isolated-salvage publication scope with `named_survivor_fit.binding(witness)`. [Driver](named_survivor_0402_trial.py) · [Tests](../../../tests/pipeline_eval/test_named_survivor_fit.py)
