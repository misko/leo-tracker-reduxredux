# Can the public Doppler fits resolve the mirrored boundary?

## Predeclared check

Earlier controls tested the constrained endpoint, a fixed-owner exterior profile, all-track reassignment, receiver agreement and an upstream point estimate. An older halo method also required agreement across disjoint orbit fits. The two radio channels here share the waveform, sky and orbit errors, so treating their votes as independent would give an unwarranted confidence gain. This check instead propagates the horizontal curvature of the existing selected likelihood after its joint radio and orbit nuisance fit. [Exterior profile](exterior-profile.md) · [All-track reassignment](regional-reassignment.md) · [Receiver veto](regional-exterior-veto.md) · [Orbit split](../../../tools/pipeline_eval/variants/region_halo.py) · [Point estimate](mirrored-regions.md)

Replay only the two original public containing offers from the saved detections, and require identical arm positions and owner digests. Freeze each arm's position and selected ownership, aliases and phase expansion. The published containing offer is an optimistic calibration-independent anchor for this diagnostic. Use it unchanged for its two shifted offers. The fit receives no containment labels, reference coordinates, or receiver heights.

Use the horizontal Hessian `H` of the selected negative-twice objective at the original endpoint, with a centered step of 25 m and a 50 m numerical check. Set the local covariance proxy to `2 H⁻¹` for a positive-definite Hessian. Use the standard two-coordinate Gaussian ellipse multiplier `χ²₂(0.95) = 5.99146`. Count a fix only if the entire ellipse is inside the offered square. Withhold as exterior if the ellipse and square are disjoint. Withhold as unresolved if they overlap without complete containment. A failed curvature check is unresolved. Apply the same rule separately for fixed-zero and fitted `c`, and require both arms to certify inside for a paired publication. Count withholds on valid offers and count confirmed exterior separately from unresolved omissions. Include the original containing square at each site as a positive control.

Report the face-normal scale `σ` from each arm's covariance and the 200 m face separation in units of `σ`. Independently evaluate the selected objective at ±200 m normal displacements with the orthogonal movement chosen from the local Hessian to minimize the quadratic objective. Average the two loss increases to cancel the original endpoint's linear term. Report RF RMS separately. The ellipse and loss comparison are conditional on this local mode and fixed associations. The nominal 95% construction does not establish coverage for the variational objective, repeated satellites, or uncertain orbital corrections.

## The saved observations leave both mirrored pairs unresolved

The `64ecfbcaf` rule retained both original containing controls. It withheld all four mirrored offers for each calibration arm and for paired publication. This withheld **2 of 2 valid boundary offers**, issued **0 of 2 false fixes**, and established exterior support for **0 of 2 omissions**. The offered-face threshold crossed an ellipse in every mirrored case. The original far-exterior veto kept both valid boundary fixes and both near omissions. [Earlier bound-gated outcomes](regional-bound-guard.md)

| Public site | Original containing control | Truth 100 m inside | Truth 100 m outside |
|---|---|---|---|
| North, both arms | Publish | Withhold, unresolved | Withhold, unresolved |
| South, both arms | Publish | Withhold, unresolved | Withhold, unresolved |

| Public site | Calibration | Face-normal σ | 95% joint ellipse half-width along the face normal | 200 m / σ | Direct 200 m objective rise |
|---|---|---:|---:|---:|---:|
| North | Fixed zero | 929 m | 2.274 km | 0.215 | 0.04631 |
| North | Fitted | 922 m | 2.256 km | 0.217 | 0.04707 |
| South | Fixed zero | 784 m | 1.920 km | 0.255 | 0.06501 |
| South | Fitted | 774 m | 1.894 km | 0.259 | 0.06682 |

The 200 m shift is about a quarter of one face-normal standard deviation under this model. Its measured average loss increase is 0.046–0.067 in negative-twice-objective units. Doubling the finite-difference step changed the face-normal scale by less than 0.02 m. The archived zero-height fits replayed exactly, including both owner digests. Frequency RMS was 5.380 versus 5.173 Hz in the north and 6.503 versus 6.392 Hz in the south, fixed zero then fitted `c`. The lower RMS in the fitted arms leaves all boundary decisions unchanged. [Northern fit](measurements/north-baseline-first.json) · [Southern fit](measurements/south-shared.json)

The ellipse describes only the selected mode with a fixed orbit catalogue, set of owners, and phase expansion. The radio and orbital nuisance fit is evaluated again at each probe, but common orbit or waveform errors can move the whole solution. This result gives an operational limit for the present Doppler fit and avoids treating uncertainty-based withholding as detection of a missing region. It leaves resolution from additional independent scans or another physical observable unmeasured. These data comprise two public simulated waveforms, with both calibration arms and all region variants reusing each corresponding waveform.

Both replays used a single low-priority core and digest-verified saved detections. They took 6.49 and 5.99 CPU seconds. The runner reads the mirrored offers only after replaying the anchor and consumes no scoring key. [Replay runner](mirrored_uncertainty_trial.py) · [Component tests](../../../tests/pipeline_eval/test_mirrored_uncertainty_trial.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock /tmp/leo-algo08v2-2x-bench/gauss.lock nice -n 15 ionice -c2 -n 7 taskset -c 2 \
  env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -B \
  reports/ALGO08/single-core-2x/mirrored_uncertainty_trial.py \
  "$site" "$saved_detections" "$public_archive" "$release/assets"
```
