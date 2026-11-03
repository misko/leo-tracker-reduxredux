# Soft shared receiver/RF offsets

Research prototype; no production changes or new RF collection. Tests whether
the few-kHz clustering seen in the preceding hard offset-transfer audit can
help jointly estimate geography, timing, and satellite-candidate probabilities.

**Decision: retain the baseline.** All 18 fits qualify, but neither fixed
prior width consistently improves held prediction or geographic accuracy.
The experiment does not establish a route to reliable sub-kilometre accuracy.

## Results

Median position error across the three existing eight-scan panels per dataset:

| Dataset | Baseline (m) | Soft offset, 3 kHz (m) | Soft offset, 10 kHz (m) |
|---|---:|---:|---:|
| DS7 | 2,023.56 | 2,073.13 | 2,031.97 |
| DS8 | 1,721.07 | 1,763.09 | 1,739.73 |
| DS9 | 876.13 | 853.69 | 862.19 |

The 3-kHz arm improves geographic error in 4/9 panels, while the 10-kHz arm
improves 7/9. However, each improves held log score in only 3/9 panels;
aggregate held-score changes are -41.608 and -23.373 respectively. Both
worsen all three DS9 held scores. Both retain exactly 2/9 sub-kilometre panels,
the same as baseline. Maximum geographic movement is 108.46 m. These small,
mixed shifts do not justify selecting the 10-kHz arm based on its geographic
win count, especially with an exposed reference.

![Position errors and held prediction changes](comparison.png)

All 4,328 tracks are retained; no observation or training/held mask is changed.
All 18 runs return successfully and pass qualification. Maximum physical
projected gradient is 0.002413; maximum finite-difference discrepancy is
8.14e-6. Increasing quadrature from 64 to 128 points changes training score
by at most 1.70e-5, any gradient component by 1.94e-5, and held score by
1.04e-5. Final fits take 15.47–31.23 seconds each, 390.14 summed process
wall seconds across three workers, excluding the preserved unscaled pilot.
All final recorded input/source hashes verify. Three test methods and Ruff
checks pass.

The direct hard-sharing failure therefore was not merely a consequence of
forbidding track-specific offsets: this particular soft, joint alternative
also fails to deliver consistent benefit. This does not rule out externally
calibrated offsets, a different physical hierarchy, or independently verified
satellite associations. Further priority should go to evidence that separates
physical Doppler from oscillator/transmitter effects, rather than choosing
another prior width using these same geographic errors.

## Model

Retain the existing Student-t4 frequency-contrast likelihood and 20%
unassociated-trend mixture. For a track with n training residuals r, define
z = r - mean(r), D = 4(100 Hz)^2 + sum(z^2), and native conversion
a = actual RF / 11.2 GHz. Under the flat-offset model, the conditional native
offset distribution is Student-t with n+3 degrees of freedom, mean a mean(r),
and scale a sqrt(D/[n(n+3)]).

Give that offset a wrapped Cauchy prior centered on a fitted lane offset μ,
where a lane is one recording, receiver, and exact RF. Period P is
1/(4.4 microseconds). For width γ, rho = exp(-2πγ/P), and the prior density
relative to the uniform offset distribution is

    W(d) = (1-rho²) / (1+rho²-2rho cos(2πd/P)).

Multiply the contrast density by E[W(a mean(r)-μ-sT)], T ~ t_(n+3).
This integrates uncertainty in each track offset, rather than treating its
sample mean as an exact independent observation. The background offset is
uniform. Both arms omit the same uniform density constant. Integer alias
shifts leave the likelihood unchanged.

Candidate probabilities remain a mixture throughout optimization. All lane
offsets, shared E/N coordinates, and eight recording time offsets are fit
together on training data. Held score is the full-vector joint mixture log
likelihood minus its training-vector log likelihood, with fitted parameters
fixed. Thus held values do not enter parameter fitting or initialization.

## Evidence and reproduction

- [Frozen protocol and numerical amendment](PROTOCOL.md).
- [Per-panel table](TABLE.md); `summary.json` includes detailed results.
- `model.py`: normalized offset likelihood, analytic derivatives, mixture.
- `test_model.py`: prior normalization, flat-prior recovery, alias invariance,
  direct integration comparison, derivatives, and held-value isolation.
- `run.py`: hash-checked inputs, training initialization, bounded local fit,
  physical-gradient and integration audits, and held scoring.
- `batch.py`: three local CPU workers with a 120-second cap per fit.
- `summarize.py`: verifies each final run's input/source hashes and produces
  the table and figure. The unscaled pilot is excluded from this verification:
  its source was superseded by the documented numerical amendment.

Run from repository root:

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_soft_lane_offset -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 120s uv run --no-project --with numpy --with scipy python reports/2026_09_29_soft_lane_offset/run.py DS7_early_8 3000
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_soft_lane_offset/batch.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with matplotlib python reports/2026_09_29_soft_lane_offset/summarize.py
```

## Limits

The nine panels are existing eight-consecutive-scan windows, not nine new
sites. Candidate banks are retained conditional hypotheses, not independently
verified satellite identities. Geographic errors use the inherited exposed,
unsurveyed reference. Widths were motivated by earlier data from these same
datasets, so this is exploratory held-observation evaluation, not untouched
dataset validation. One local initialization per width does not establish
global optimality. This prior tests statistical offset consistency and does
not identify an oscillator error, prove a sequence-to-satellite identity,
or establish an absolute frame timestamp.
