# Candidate-group influence on eight-scan localization

**A small candidate group can substantially influence location, but automatic
downweighting is not yet justified.** Among eight qualified half-weight fits,
six improve geographic error and all eight improve held prediction on the
remaining tracks. Seven nevertheless worsen total held log score. Keep the
baseline; investigate joint errors across tracks assigned to the same candidate.

## Experiment and outcome

At each cached optimum, compute the score gradient of every track, including
the full satellite/background mixture. Group tracks by their training-favored
candidate only when candidate probability times signal responsibility >=0.5.
Use the previously audited observed Hessian to predict the location response
to halving each group's weight. Select the largest response without consulting
held values or the location reference. Freeze that selection and refit E/N and
all eight recording times. Each track still has its full candidate mixture.

The original cross-scan support gate stopped the first panel before any fit.
The documented coverage amendment allows repeated tracks within a scan. In all
nine panels the selected group spans only one scan, so these results do not
establish a persistent satellite-specific orbit correction across scans.

| Panel | Selected tracks | Baseline error, m | Half-weight error, m | Qualified |
|---|---:|---:|---:|:---:|
| DS7 early | 4 | 2,286.00 | 1,862.77 | No |
| DS7 middle | 9 | 1,603.57 | 1,528.92 | Yes |
| DS7 late | 9 | 2,023.56 | 1,755.16 | Yes |
| DS8 early | 7 | 1,435.66 | 1,239.79 | Yes |
| DS8 middle | 7 | 2,130.85 | 1,953.25 | Yes |
| DS8 late | 6 | 1,721.07 | 1,813.21 | Yes |
| DS9 early | 4 | 639.50 | 902.80 | Yes |
| DS9 middle | 6 | 876.13 | 369.92 | Yes |
| DS9 late | 10 | 3,680.86 | 2,852.39 | Yes |

DS7 early returned an abnormal optimizer termination despite a small gradient
and passing derivative audit. It remains unqualified under the frozen rule;
its displayed endpoint is diagnostic, not a certified optimum. The six-of-eight
geographic improvement count excludes it. The other eight retain two sub-km
panels, unchanged from their baseline. No aggregate DS7 median is promoted from
an incomplete qualified set.

[Full table](TABLE.md) includes candidate numbers and held-score gains split
between selected and remaining tracks. The held score uses the original,
unweighted model on all original held observations at the new location/times.
The selected tracks lose held score in every panel. Only DS8 early improves
total held score (+17.244); geographic improvement alone is insufficient.
The interleaved held partitions are not independent new recordings.

## Interpretation and next decision

This measures a conflict between one training-selected group and the remaining
data. It does not show which is physically correct. Selection by influence can
favor such conflicts; all remaining tracks improving their held score does not
prove the selected candidate is wrong or its tracks are duplicates. Candidate
identities remain conditional hypotheses, and the geographic reference is the
inherited exposed, unsurveyed location.

A useful next model would represent shared error among tracks assigned to one
candidate within a recording, rather than treating them as independent evidence
or fitting an unconstrained slope per track. Any such model must retain the
geographic sensitivity identified in the previous candidate-information study
and validate predictions for entire held-out groups or recordings. The present
weighted objective is a diagnostic composite likelihood, not that joint model.
Do not choose which group to suppress based on these geographic errors.

## Verification and reproduction

All nine panel commands returned zero. All eighteen +/-1% weight fits qualify
and pass the local influence-response audit. Eight of nine half-weight fits
qualify; the single failure is preserved. Every track-gradient sum reproduces
the baseline gradient within 1e-7. Input artifacts and inherited model/Hessian
source bindings are checked, and the summary verifies final per-run hashes.
The synthetic test checks the influence sign against an exactly solvable
quadratic optimum and finite-differences the weighted objective gradient.

Files preserve every eligible group's membership, score gradient and predicted
influence, all 27 fits and messages, derivative audits, response audits, held
splits, and timings. [Protocol](PROTOCOL.md) records the coverage amendment.
No observations, production code, golden fixtures, or radio data were changed.
These reports are local and have not been pushed.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_candidate_influence -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 90s uv run --no-project --with numpy --with scipy python reports/2026_09_29_candidate_influence/run.py DS7_early_8
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_candidate_influence/batch.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy python reports/2026_09_29_candidate_influence/summarize.py
```
