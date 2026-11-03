# Track-level fitting, candidate retention and timing initialization

Recording: `fast8-auto-20261016-161535-99008d35-1-lower`.

The investigation remains incomplete. This iteration found a concrete loss of a plausible satellite candidate between cold discovery and final fitting, implemented and tested a grouped-track likelihood, and made its fitting and checkpoint audit commands independent of the old temporary investigation scripts. It has not produced a model that recovers all three trajectories in both cold temporal folds.

The previously accepted forward joint model remains the best verified three-track recovery: 63/63 withheld points retain the training-selected assignments, with 133/144/123 Hz carrier RMS for early CH2/CH4/late CH2. These are frequency and association results, not independent satellite identity truth or geographical accuracy.

## A candidate was proposed and subsequently discarded

Cold discovery evaluates the full regional TLE bank and proposes candidate subsets at spatial search points. The final candidate bank is rebuilt from bootstraps at the admitted source centers; it does not preserve every earlier discovery proposal.

For the reverse fold, the union of the 24 discovery-point receipts contains 105 candidates. Candidate 69333 appears at seven of those points, but is absent from the 60-candidate final bank. Thus the final fit cannot assign any observation to it. This is the candidate favored for CH4 by the successful forward calibration; its presence is a plausible alternative, not independent identity truth. The forward fold retains all three forward-consistent hypotheses in its final bank.

![Candidate support before and after final-bank construction](01_candidate_retention.png)

The audit is reproduced from hash-verified discovery-point receipts and terminal checkpoints in the adjacent replay capsule. The retention experiment first preserves the union of all discovery candidates and the original final bank, without inserting a hand-picked ID. This is 103 candidates forward and 105 reverse. The larger fits fail to converge within many of the original 60-second solver allowances and do not by themselves solve recovery.

## Grouped final likelihood

The new research component removes the supplied training-track rows from the independent background mixture and replaces them with one joint likelihood per track. Each track has one latent satellite identity shared across all its observations. Background points retain the previous independent satellite/clutter mixture. Receiver band offsets, position, calibration, satellite timings and background detectability remain fitted.

For one track, residuals are the measured-minus-predicted carrier differences, modulo the 227,272.727 Hz alias period. Each candidate has a wrapped Gaussian emission with 125 Hz sigma. The likelihood multiplies emissions across the track before summing over candidate identity. A normalized geometric mean of the fitted smooth visibility weights supplies the identity prior, with an explicit numerical floor of `1e-12`.

This conditions on the supplied group being a real single-satellite track and therefore has no clutter alternative inside that group. It supplies track membership, not satellite labels. A posterior of one merely says one candidate is much less bad than the others under this assumption: several failed fits have probability one and multi-kilohertz withheld error. Independent prediction checks remain mandatory.

The kernel includes neighboring wrapped Gaussian images explicitly. Dropping them in a no-clutter log likelihood gives the wrong value and derivative at an alias boundary even when the ordinary clutter mixture would underflow those terms to zero. A dedicated unit test covers that edge case; it is not asserted to explain the three observed trajectories.

## Training-only timing proposals and a bounded candidate bank

Simple clipping of inherited satellite timings to ±3 seconds can leave a viable candidate far from a real trajectory. The next initialization searches every discovery candidate over ±5 seconds in 0.05-second steps, using only each supplied training half and the same two-second timing prior for every candidate. The best training proposals initialize satellite timing; final identities remain latent.

An additional bounded variant retains every original final-bank candidate plus every training-winning proposal from the discovery union. It preserves trained detectability for existing candidates and records any bounded-coordinate projection when candidates are added. This keeps 54 candidates forward and 61 reverse, rather than carrying all 103/105 candidates indiscriminately. No satellite number is coded into this selection.

Both independent-point and grouped-track models receive identical data-dependent initialization within each comparison, including the common cold fitted-`c` calibration and timing-proposal conditioning. Both RF arms use the same observations, bank, priors and allowances. Initial background timings are clipped to ±3 seconds; accepted training proposals can initialize timing anywhere in the declared ±5-second proposal domain. Fitting retains the original ±20-second per-satellite physical bounds, the original 250 km spatial prior, and a 0.5-second relative timing prior. Each stage allows a 60-second fitter within 65 seconds total; continuations and numerical polishing are recorded separately.

## Results and numerical qualification

The smaller-bank grouped model reaches an accepted reverse-fold endpoint, but does not recover the three forward-consistent identities. Its fitted-`c` withheld RMS is 1,576/172/2,226 Hz, compared with 1,475/388/2,147 Hz for the original reverse cold search. CH4 frequency prediction improves, while the other two trajectories remain poor. Both the baseline and grouped reverse model choose 57149 for CH4; that agreement does not establish its true identity.

Forward frequency predictions with training timing proposals are promising, but several endpoints stop above the unchanged 0.001 stationarity gate. A separate 30-second numerical polish tightens the optimizer tolerance from `1e-11` to `1e-14`, without changing the model, priors, bounds or audit threshold. It still does not qualify the tested forward models. Their low errors remain rejected diagnostics, not promoted results.

![Latest proposal-based fits and unchanged numerical qualification](02_grouped_temporal_rms.png)

The JSON results retain both fitted-`c` and `c = 0` controls, original attempts, continuations, and failed endpoints. Objectives from grouped and independent likelihoods have different observation assumptions and are not ranked against each other as if they were the same likelihood. Frequency scores and held prediction errors do not establish position accuracy.

## Spatial-search priority control

A fresh reverse-fold pipeline run used the identical training-input bytes, pinned TLE snapshot, 24-point discovery budget and 480-second whole-pipeline bound, changing only adaptive spatial-search priority from all channels to CH1–4. It completed in 334.41 seconds with an accepted endpoint, but withheld full-catalogue candidate searches still give 2,066/485/1,135 Hz. Simply prioritizing the lower band does not repair the failure. It also drops 69333 from the final bank. The first launcher attempt failed before inference because the discovery override addressed the CLI module instead of the application module; that wiring was corrected and a new attempt namespace was used.

## Reproduction and tests

The component owns seven density/group tests and two independent known-optimum optimizer tests. The fitting driver checks analytic derivatives for spatial, calibration, timing, clock, receiver-band and detectability coordinates on actual cold-training inputs. Its independent endpoint audit retains feasibility, objective closure and the 0.001 stationarity gate.

The portable audit command has been executed on an accepted reverse grouped checkpoint and a rejected forward grouped checkpoint. Both reproduce their original objective, withheld residuals, assignments and numerical acceptance outcome. Passing replay does not turn a rejected or poorly predicting model into a successful recovery.

`fit.py` loads the original export and pinned TLEs through the adjacent replay capsule; it does not read the old temporary investigation scripts. Use the installed interpreter and package path documented in the [replay capsule](../three-track-recovery-replay-20261016/report.md), then run:

```bash
python fit.py --input /path/to/original-export.json --tle-root /path/to/tle-archive \
  --fold early_to_late --variant coherent --arm fitted-c \
  --retain-discovery --training-timing-seed --proposal-closure \
  --output /new/attempt/result.json
```

`--audit-checkpoint /path/to/result.json` independently rebuilds the model and recomputes its audit and held predictions without fitting. `--pass-number 2 --resume /path/to/first-result.json` gives an explicit second bounded allowance. `--polish-checkpoint` is a separate numerical diagnostic with its own recorded budget. Each output filename must be new. The output records all proposal identities, timings, candidate numbers, derivative checks, fit parameters, numerical acceptance and withheld residuals.

No production code or automatic scan processing has been changed. The next model work must address joint calibration/source ambiguity rather than assuming candidate retention or within-track identity coherence alone is sufficient.
