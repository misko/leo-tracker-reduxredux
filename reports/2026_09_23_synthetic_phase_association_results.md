# Synthetic phase association improves calibrated log loss and abstains under mismatch

The supervised observation-level qualification met its prespecified condition.
In the calibrated held scenario, phase reduced mean true-candidate log loss from
0.0888 to 0.0520 at 100% coverage. Top-one accuracy remained 17/18 for both the
Doppler baseline and augmented scorer, so the gain is better probability assignment,
not another correctly identified trajectory. The fixed 90-degree orientation
control scored worse at 0.0747 log loss. Orientation was a frozen diagnostic,
not part of the prespecified success condition; this comparison is descriptive.

Under source/frequency-dependent phase mismatch, training residual concentration
was 0.0257 with 1.833 rad RMS, so the fixed authority gate disabled phase. Under
independent source phase, concentration was 0.157 with 1.686 rad RMS and phase
was also disabled. Both held scenarios retained zero phase coverage and exactly
the Doppler baseline scores. These abstentions use only supervised outer-training
residuals; held labels never enter candidate losses.

| Declared scenario | Phase coverage | Doppler top-one | Augmented top-one | Doppler log loss | Augmented log loss | Orientation-control log loss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Calibrated | 100% | 17/18 | 17/18 | 0.0888 | 0.0520 | 0.0747 |
| Frequency/source mismatch | 0% | 17/18 | 17/18 | 0.0888 | 0.0888 | 0.0921 |
| Independent phase | 0% | 18/18 | 18/18 | 0.00461 | 0.00461 | 0.00464 |

The [protocol](2026_09_23_synthetic_phase_association_protocol.md), scorer, and
tests were frozen at `1175f8de`; corrected source hashes were committed at
`2815a951` before generation. The original seal was superseded before any full
population or held outcome was generated and remains preserved. Seed 20260930
assigns the same random 18/18 whole-trajectory outer split in each separately
declared scenario. The complete run took 0.09 seconds.

The simulator generates two-source, two-receiver phase first and derives the
double difference, so shared receiver drift cancels algebraically while
source-dependent mismatch survives. Candidates are created from latent state
before observation noise. Their opposite cross-track perturbations change phase;
small opposing range-acceleration perturbations retain a difficult but nonexact
Doppler distinction after calibration offsets. One local phase intercept and
candidate-independent Doppler offsets use random calibration times; response
times alone determine candidate loss.

This is actual progress on scorer behavior: with phase authority, phase improves
held probabilistic discrimination over Doppler alone, and descriptively also
beats the frozen wrong-orientation control; when training shows the phase
model is invalid, the scorer abstains rather than degrade held association. It is
not evidence that saved-IQ extraction reaches this observation model. Training
uses known labels to estimate scales and authority separately for each declared
sensor scenario. Real deployment therefore needs external calibration authority,
and real validation still needs independently labeled same/different-source
tracks. The counterfactual 8 cm baseline and analytic trajectories are sensitivity
fixtures, not measurements of the hardware or sky.

These are four-second scenarios; a 20 ms expected-null experiment was discussed
but is not part of this frozen evaluation. Generation and scoring share the
same geometric family, so the calibrated result is an internal qualification,
not robustness to orbit-model error. Each mismatch experiment supplies matching
labeled training data: abstention here does not prove detection of a new receiver
fault appearing only after training. The 90-degree control is a frozen diagnostic,
not an additional success criterion introduced after viewing results. Eighteen
held trajectories and one random split do not establish a population-level gain.

Validation: four focused tests passed, including a held-label mutation check
that leaves candidate losses unchanged. Terra independently reviewed the final
scenario separation and supervised-calibration assumptions.
No bootstrap uncertainty was prespecified, and 18 held units per scenario are
too few for a precise generalization estimate. Results also depend on the fixed
analytic LOS/range-rate model, Gaussian observation noise, candidate construction,
and supervised scenario authority. They show no real association or position gain.

Artifacts: [corrected seal](figures/2026_09_23_synthetic_phase_association/seal-v2.json)
and [complete result](figures/2026_09_23_synthetic_phase_association/result-v2.json).
