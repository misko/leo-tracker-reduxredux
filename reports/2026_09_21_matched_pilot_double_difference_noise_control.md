# Noise control required for overlapping matched-pilot double differences

The existing exact-time waveform estimator uses separated 12 kHz subbands.
A proposed known-pilot estimator would instead correlate two templates against
the same broadband samples. More known symbols provide a possible improvement,
but overlapping templates introduce a distinct noise bias that must be tested
before interpreting a near-zero double difference as geometric evidence.

## Analytic noise-only counterexample

Let normalized templates be `t_A` and `t_B`, and let receiver noises `n_0`
and `n_1` be independent, zero-mean, circular complex Gaussian vectors with
covariances `sigma_0^2 I` and `sigma_1^2 I`. Define

```
m_rs = t_s^H n_r
z_s  = m_1s conjugate(m_0s)
q    = z_B conjugate(z_A)
```

Even with no transmitted signal,

```
E[q] = sigma_0^2 sigma_1^2 |t_B^H t_A|^2.
```

Thus same-sample matched filtering followed by the fourth-order phase product
can yield an apparently coherent zero-phase result from noise alone. The
effect grows with template correlation. It is not removed merely by using
independent receiver noise, simultaneous samples, or more bootstrap draws.

An independent numerical check used 300,000 realizations with NumPy seed
20260921. For each receiver, unit-variance complex normal variables `a` and
`e` gave `b = rho*a + sqrt(1-rho^2)*e`. The measured statistic was
`b_1 conjugate(b_0) conjugate(a_1) a_0`.

| Template correlation rho | Expected mean | Observed complex mean | Normalized magnitude of summed products |
| ---: | ---: | --- | ---: |
| 0.0 | 0.000 | -0.00064 - 0.00163 i | 0.00285 |
| 0.5 | 0.250 | +0.25016 + 0.00025 i | 0.35770 |
| 0.9 | 0.810 | +0.81281 + 0.00018 i | 0.88829 |

This is a counterexample for the proposed estimator, not a diagnosis that the
existing disjoint-subband results have this particular bias. Non-white or
cross-receiver correlated noise requires a more general covariance treatment.

## Required validation before a saved-IQ claim

A pilot-based extension must check its actual template Gram matrix and leakage
and pass noise-only, one-source-only, and two-source nonzero-phase injections.
The two-source injection must include unequal amplitudes, common receiver
phase/frequency evolution, and the source timing offsets seen in the capture.
Any covariance subtraction or independent-sample construction must be explicit
and validated; a bootstrap around a biased statistic cannot correct the bias.

Corrected raw frequency authority and a common phase reference are still
required across both source extractions. Shared timing and a high pilot/control
ratio alone do not validate the fourth-order double-difference observable.
No production estimator or saved-IQ product was changed for this calculation.

## Cross-receiver correlated residuals survive the first correction

Subtracting the exact within-receiver covariance from each source cross term
is sufficient for the independent-receiver Gaussian null above, but not for a
shared residual. For unit-variance matched outputs let

```
C_r = m_rB conjugate(m_rA) - E[m_rB conjugate(m_rA)]
```

For jointly proper Gaussian noise, the remaining expectation is

```
E[C_1 conjugate(C_0)]
  = E[m_1B conjugate(m_0B)] E[m_0A conjugate(m_1A)].
```

If both cross-receiver correlations equal a real kappa, this is `kappa^2`.
Another 300,000-realization check (seed 20260922, within-receiver template
correlation 0.5) gave corrected mean real parts 0.00115, 0.24804, and 0.80441
for kappa 0, 0.5, and 0.9 respectively, versus expectations 0, 0.25, and 0.81.

Thus a joint-template least-squares estimator with within-receiver covariance
subtraction still needs residual cross-receiver diagnostics and qualified
pilot-versus-control evidence. Shared residual energy cannot automatically be
classified as independent receiver noise. Disjoint sample splits likewise do
not establish independence when the residual is temporally correlated.
