# Screen three initial v5 branches, then finish the winner

Both screens completed all six recordings and cut the initial phase-refresh fits from 15 to 9 per recording. They kept the original winning rank and exactly reproduced both cavity coordinates and conditional Doppler RMS values from their respective five-refresh optimizer controls. The stock-optimizer screen selected rank 1 on DS26-0036 and rank 0 on the other five, as did the secant screen. [Sealed predictions](receipt.json) · [Per-recording scores](per-recording.csv)

Ordinary v5 fits each of three ranked initial assignments for five phase refreshes. The screen fits all three for two refreshes, selects the lowest zero-calibration loss, and resumes that assignment from its saved position and clipped phases for three more refreshes. The stock-optimizer and secant methods apply the same screen. They each supply the selected initial assignment to the same paired conservative, phase-history, signed and cavity policies, with the original late refresh budgets. [Screening implementation](../../../tools/pipeline_eval/variants/v5_screen_winner.py) · [Protocol](PROTOCOL.md)

The six cases come from the earlier compact-v5 timing cohort at one roof installation. The small-sample measurements use the stored native detector factors, the causal catalogue, the fixed tile and both calibration arms. The rank audit supplies the original stock-optimizer winning rank. The matching endpoint controls are the published five-refresh compact projector and five-refresh secant receiver. Their original receipts use different names for the public case digest and archived request digest. The source lock binds both hashes along with the native input, catalogue and both region centers. [Input and source lock](source-lock.json) · [Archived projector trial](../../2026_11_19_receiver_convergence/phase-budget/README.md) · [Archived secant trial](../../2026_11_19_receiver_convergence/position-fit/README.md)

## Position accuracy and coverage

All six recordings supplied a fix within 2 km in both calibration arms for both screens and all four original v5 references. Each screened arm placed four of six fixes within 1 km. Observation counts, track counts and cavity eligibility agreed with the matching optimizer controls on all six recordings. [Per-recording geography and coverage](per-recording.csv) · [Summary](scores.json)

| Method | Zero-calibration median (km) | Zero-calibration P95 (km) | Fitted-calibration median (km) | Fitted-calibration P95 (km) |
| --- | ---: | ---: | ---: | ---: |
| Stock-optimizer screen | 0.819 | 1.309 | 0.832 | 1.395 |
| Secant screen | 0.818 | 1.305 | 0.831 | 1.392 |
| Original v5 baseline | 0.819 | 1.309 | 0.832 | 1.395 |
| Original v5 selective gap | 0.819 | 1.309 | 0.832 | 1.395 |
| Original v5 omit one track | 0.780 | 1.309 | 0.794 | 1.395 |
| Original v5 omit tracks | 0.780 | 1.309 | 0.794 | 1.395 |

## Conditional frequency fit

The median conditional RMS was 78.443 Hz at zero calibration and 78.409 Hz with fitted calibration for the stock-optimizer screen. It was 78.518 and 78.484 Hz for the secant screen. Every per-recording RMS matched its optimizer control exactly. Fitting calibration lowered median RMS for both methods while their median geographic error increased. [Arm-level results](per-recording.csv)

## Timing

The fresh same-CPU comparison measures the effect of substituting secant for the stock optimizer under the same screen. The median paired ratio was 1.17× for initial-stage CPU and 1.34× for whole-worker CPU. The corresponding wall ratios were 1.22× and 1.37×. Residual evaluations across all six recordings fell from 14,424 to 3,752 in this comparison. [Timing and work counts](scores.json) · [Stock-optimizer predictions](v5_screen_winner-positions.jsonl.gz) · [Secant predictions](v5_screen_secant-positions.jsonl.gz)

| Recording | Initial CPU s, stock → secant | Initial wall s, stock → secant | Whole CPU s, stock → secant | Whole wall s, stock → secant |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 20.23 → 15.95 | 20.95 → 16.36 | 109.02 → 74.56 | 113.94 → 76.72 |
| DS26-0122 | 45.29 → 25.06 | 47.04 → 25.19 | 310.54 → 128.54 | 358.54 → 131.90 |
| DS26-0237 | 21.66 → 19.24 | 22.59 → 19.95 | 110.48 → 87.84 | 112.29 → 90.63 |
| DS29-0082 | 7.37 → 7.87 | 7.57 → 8.39 | 52.54 → 49.72 | 56.04 → 51.78 |
| DS29-0174 | 21.52 → 17.83 | 22.16 → 19.18 | 119.54 → 87.30 | 124.91 → 91.45 |
| DS29-0247 | 38.06 → 38.33 | 61.76 → 45.67 | 173.27 → 131.86 | 209.41 → 151.83 |

Whole-worker time includes projector kernel compilation, worker launch, native preparation and inference through the cavity decision. Initial-stage time includes cold branch ranking and all subsequent initial fits. Comparing against the earlier five-refresh measurements gives descriptive median initial wall ratios of 1.36× for the stock optimizer and 1.15× for secant. The archived projector measurement used an additional outer CLI process on the same CPUs, and the archived secant timing used different CPUs. These separate sessions establish the scientific controls and the 15-to-9 reduction in fits. The fresh paired timings above measure the optimizer change under screening. [Timing scopes and archived measurements](scores.json)

The qualification harness sealed all twelve candidate results before opening the evaluation-coordinate references. The worker-source archive matches the original lock. A post-seal correction to scoring made threshold counts reuse the full list for each radius and fixed the CSV export call. The qualification validator also checks the reported minimum rank and accepts a recorded full-budget fallback. The twelve evaluated legs all used the ordinary nine-fit path. [Qualification harness](../../../tools/pipeline_eval/qualification/winner_screen_eval.py) · [Sealed worker sources](sealed-worker-sources.tar.gz)
