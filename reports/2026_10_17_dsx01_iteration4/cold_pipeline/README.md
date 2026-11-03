# Faithful original S03 cold-half baseline

The original production pipeline passes strict training admission but associates only 165/1982 held observations (8.32%), versus 1571/2006 training observations (78.32%). The two held requested windows retain 2/84 observations. This is negative prediction evidence from one source/fold, not a result on new recording positions.

One unmodified `leo.cli.shared_fast_position.run(...maximum_seconds=480,tle_root=...)` completed in 77.659 seconds. Policy: `generic-cold24-shape3-fresh-six-ab-v1`. Selected source `B-all` has strict KKT 0.000223167414; training objective 20439.928967 and frequency NLL 20172.654526. No local-segment/v6 replacement, saved full-fit position/calibration/bank, production write, or RF collection was used.

The split uses complete probe intervals around the immutable capture-counter midpoint (149.9750442 s). It retains 3740 probes and excludes 3760 held probes; 0 straddle the cut. Every candidate measurement in an excluded probe is removed before preparation, bootstrap or discovery. Original clock anchor, delivery clocks, counter/RF and parent provenance authorities remain fixed. Four prelaunch tests and a real-source perturbation of every excluded CFO, score and gate gave identical training bytes and preparation evidence. Training digest: `sha256:29072595aef75f46a70aada310d8b788c11e76f1a71197daf8945de447c219f3`. All 2006 train IDs occur in the frozen original 3988-observation S03 cohort. The previous median-observation split used 149.046963095 s and 1994/1994 observations; it is a different protocol. Historical 63/66-target-probe exclusions are also different. Holding the complete timing authority is metadata conditioning, not access to held CFO. No held CFO enters a seed, calibration or discovery. 

The public latest-before-origin-minus-505-seconds archive policy selects **space-track**, `sha256:d07c22e355ffbe4699bc4be9de9f330c0eef3e44b74f6d200b1cb14502dffbe7`, collected at 1792181063706395625 UTC ns. A fresh TRAIN-only regional bank has 708 candidates; discovery selects 25 IDs. Only these selected IDs are propagated for full-domain evaluation. The full prediction bank exactly reproduces its training overlap; every held row receives finite predictions. This experiment is training-discovered, whereas previous restricted prototypes were conditioned on the full-recording selected bank.

The learned high-minus-low offsets are -15389.413 and 41224.229 Hz. The original calibration class is present; offsets are not forced to zero. Residual-clock nodes 0,30,…,150 s extend to 300 s with the boundary residual held constant. Every learned affine term, slope and RF dependence remains unchanged; no new held knot is fitted. Complete training correction closes within 3.64e-12 Hz, and training frequency NLL replays exactly. Constant residual-clock extrapolation is a declared prediction assumption, not evidence that the hardware clock remains constant.

| Evaluation cohort | Associated | Assigned RMS Hz | Conditional CFO NLL |
|---|---:|---:|---:|
| Train | 1571/2006 | 151.11 | 20172.65 |
| Held | 165/1982 | 173.73 | 26902.97 |

| Fixed requested window | Train associated | Held associated |
|---|---:|---:|
| DSX01-007 | 54/54 | 0/0 |
| DSX01-008 | 0/0 | 2/50 |
| DSX01-009 | 0/0 | 0/34 |

All 25 selected IDs have positive model visibility in both halves. No held row has zero visible selected candidates; visible q mass is 1.6 throughout. All 23 IDs with assigned training support remain visible held. Nearest circular residual to any visible selected prediction has median 130.86 Hz train and 5396.08 Hz held; 1560/2006 train versus 177/1982 held lie within 375 Hz. Thus empty visibility or an uncovered propagation interval does not explain the failure. Positive visibility does not prove that the actual emitter is among the selected IDs. The audit cannot uniquely separate missing correct identities from timing/calibration extrapolation. Assigned labels are model hypotheses, not verified identities. Per-ID and 30-second-bin diagnostics are saved without any refit.

The fitted location is (37.975789, -122.883183), 37.606 km from the matching configured station reference. The reference is uncertain, unsurveyed and used only after prediction freeze. Frequency fit does not establish localization accuracy.

Cost: 7540 exact A/B/shared objective calls across 26 fits, plus 6 prescreens. Discovery has 24 points/72 fit receipts (71 converged), 15382 reported solver evaluations and 17.767 summed fit seconds. There are 3 shape attempts and 18 bootstrap stages. Discovery/shape/bootstrap counters are separate; the terminal's `cost_exact=true` covers its stated A/B/shared scope, not every algorithm call. All counted fits respect their declared 2000-call/20-second source or 5000-call/65-second shared allocation. The original whole policy reserves discovery 240 seconds, bank 180, shape 20 per view, bootstrap 5 per stage, and 130 seconds for finals under the 480-second outer cap. All actual stage receipts remain available; no unfinished stage or retry occurred.

The original pipeline fits c during source generation. There is no whole-pipeline c=0 comparison here, and no fitted-c localization advantage is claimed. A later matched downstream c=0 sensitivity would be conditional on this fitted-c discovery. The earlier zero-contrast stress tests and donor/grid prototypes remain separately labeled.

Six final component tests pass. A no-fit independent replay exactly reproduces saved predictions, associations, residuals, strict endpoint metrics, prior/clock closure and separately scoped cost bounds. Raw attempt receipts remain immutable.

![Training versus held coverage](cold-coverage.png)

Entrypoints: `run_original.py --run` creates the one immutable attempt and refuses reuse; `evaluate.py` freezes predictions before loading held CFO for scoring; `evaluate.py --verify` audits saved output without fitting; `support_diagnostics.py` is a fixed-prediction visibility/frequency audit. No additional pipeline run is authorized by this report.
