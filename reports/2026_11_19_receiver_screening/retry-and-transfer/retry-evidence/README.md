# Can primary pilot evidence select the retries worth running?

The frozen signal rule skipped **25.9%** of eligible retries on the later DS26 block and **31.4%** on the new DS29 recording. At the same attempt counts, the independent time-spread control recovered **7 more** receiver-probes on DS26 and **5 more** on DS29. The local primary evidence did not improve rescue retention at the tested budgets. [Retry comparison](stage.pdf) · [Complete attempt counts](retry-outcomes.csv)

An opportunity occurs when exactly one receiver passes the original fractional gate on its 12-anchor primary. The rule retries its peer when the failed receiver's largest complete fractional margin reaches **0.005** and the passing receiver's margin reaches **0.25**. Both inputs are available from the current visit before the retry. The established detector retries on every such opportunity. The time-spread control independently chooses one visit from each equal-count chronological interval, using the signal rule's total attempt count for that partition. [Frozen rule](policy-lock.json) · [Protocol](PROTOCOL.md)

| Case | Every retry, attempts / rescues | Signal rule | Same-count time-spread |
| --- | ---: | ---: | ---: |
| DS26-0237 visits 0–3383, development | 731 / 206 | 553 / 158 | 553 / 152 |
| DS26-0237 visits 3384–6767, held | 861 / 242 | 638 / 176 | 638 / 183 |
| DS29-0082, prospective transfer | 1,010 / 228 | 693 / 145 | 693 / 150 |

The early DS26 block determined the policy. The best of 157 presets retained **76.7%** of rescues and saved **24.4%** of attempts, falling short of the preset 80% retention and 25% savings together. The policy lock was written at 23:42:38 UTC, before the new DS29 primary factors were sealed at 23:45:06 UTC. Every eligible retry counts, including the **619** unsuccessful ones in the DS26 held block and **782** on DS29. The late DS26 comparison uses previously sealed complete factors. DS29 uses the newly replayed 12-anchor factors on all original retry visits and the authenticated complete conditional stream. [Development ladder](development-ladder.json) · [DS26 source and decisions](receipts/DS26-0237/selection.json) · [New DS29 replay seal](receipts/DS29-0082/upstream-primary-lock.json)

## Whole-recording compact positions

Both policies produced four fresh matched compact fits on complete recording inputs. The DS26 fits include the development block. They preserve both physical receivers, original validity and clock exclusions, the original causal catalogue, the offered region, and the search budget. The every-opportunity comparator comes from the earlier measured compact fits. [Pre-score position seal](prediction-lock.json) · [Compact service clocks](position-timings.json)

| Recording and policy | Error at `c = 0` (km) | Error with fitted `c` (km) | RF RMS zero / fitted (Hz) |
| --- | ---: | ---: | ---: |
| DS26 every retry | 0.353 | 0.262 | 80.67 / 80.61 |
| DS26 signal rule | 0.420 | 0.340 | 84.29 / 84.25 |
| DS26 time-spread | 0.488 | 0.391 | 81.12 / 81.08 |
| DS29 every retry | 0.568 | 0.516 | 97.00 / 96.68 |
| DS29 signal rule | 0.721 | 0.988 | 77.58 / 77.43 |
| DS29 time-spread | 0.895 | 1.395 | 77.58 / 77.42 |

The signal rule located both roofs closer than the same-count control under both calibration settings. Both selective policies exceeded the errors of all four original v5 options by more than 10% in both arms. On DS29 the signal rule's fitted `c` lowered the RF RMS by 0.15 Hz and increased error by 267 m. [Position and frequency scores](scores.csv) · [Four original v5 options](v5-controls.csv) · [Zero calibration chart](charts/c0/modifications.pdf) · [Fitted calibration chart](charts/fitted_c/modifications.pdf)

## Reproduction

The trial module freezes thresholds from DS26 and assembles complete factor streams for each frozen policy. For an independent repeat, copy the published `policy-lock.json` into a new scratch directory and run `prepare` first. The DS29 invocation takes the primary and conditional paths pinned in its selection receipt. Run `retry_evidence_position` with the scratch directory and case ID. Run `retry_evidence_results` on the completed position receipts to reproduce the charts. The detector-stage comparison counts omitted retry calls from authenticated factors. The separately recorded position service timings are fresh host measurements. [Trial command](../../../../tools/pipeline_eval/qualification/retry_evidence_trial.py) · [Position command](../../../../tools/pipeline_eval/qualification/retry_evidence_position.py) · [Component tests](../../../../tests/pipeline_eval/test_retry_evidence.py)
