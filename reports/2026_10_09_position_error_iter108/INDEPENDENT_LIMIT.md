# An exactly nested, linear-cost persistence model

This is a derivation from the existing hard60 likelihood, not an implemented
position experiment or evidence that persistence improves accuracy. The ambiguity
audit in [PREPARATION.md](PREPARATION.md) should determine whether to pursue it.

Let `K` be the fixed candidate-bank size, `q = detection_budget/K`, `v[n,s]`
the current visibility mask, `lambda` the clutter rate, and `A` the alias width.
The current per-window density factor is

```
L[n] = p0[n] / (1 - p0[n]) *
       (lambda/A + sum_s v[n,s] * q/(1-q) * Gaussian[n,s])
p0[n] = exp(-lambda) * (1-q) ** sum_s v[n,s]
```

The implementation uses the nearest wrapped Gaussian in the narrow-width regime.
Any prototype must use the same convention for exact numerical nesting.

Separate the categorical identity mixture from the original detection factor:

```
C[n]       = lambda + sum_s v[n,s] * q/(1-q)
pi[n,0]    = lambda / C[n]                       # clutter state
pi[n,s]    = v[n,s] * q/(1-q) / C[n]             # satellite states
f[n,0]     = 1/A
f[n,s]     = Gaussian[n,s]
D[n]       = p0[n] / (1-p0[n]) * C[n]
L[n]       = D[n] * dot(pi[n], f[n])
```

This retains the complete original detection normalization. Merely replacing
responsibilities with a normalized mixture would omit `D[n]` and introduce a
different preference for visible satellite counts.

For a short, eligible track segment, define `a[n,s]=1` only for satellite states
visible at the current window. Set `a[n,0]=0`: clutter always resets. A previous
satellite that becomes invisible also resets instead of retaining probability
in a state that cannot currently produce a signal. With one global `rho` in
`[0,1)`, a normalized transition is

```
T[n,i,j] = rho*a[n,i]*indicator(i==j) + (1-rho*a[n,i])*pi[n,j]
```

Each row sums to one. For normalized previous filtered probabilities `alpha`,
the prediction and update can be computed without a dense transition matrix:

```
sticky[j] = rho * a[n,j] * alpha[j]
reset     = 1 - sum_j sticky[j]
beta[j]   = sticky[j] + reset*pi[n,j]
z[n]      = dot(beta, f[n])
alpha[j]  = beta[j]*f[n,j]/z[n]
log_score += log(D[n]) + log(z[n])
```

At the first window of each segment, or any gap/RF/channel/receiver reset,
use `beta=pi[n]`. Uncovered and overlapping-track rows remain independent.

At `rho=0`, every `beta` equals its current `pi`, so every window contributes
exactly the original `log(L[n])`. Thus the original score is recovered for all
windows, not only the subset inside tracks. Both forward and backward recursions
cost O(NK); memory can be bounded by the short-segment policy.

Away from visibility boundaries, `pi`, `D` and `a` are locally constant with
respect to the fitted parameters. The derivative of the sequence log likelihood
with respect to a predicted satellite frequency is its smoothed state occupancy
times the ordinary Gaussian derivative. For the negative log objective, the
prediction gradient is `-gamma[n,s] * residual[n,s] / sigma**2`, matching the
current per-window prediction-gradient interface. Existing timing and clock penalties
stay unchanged. Visibility transitions are discontinuous in the original model
too; a prototype must not claim derivatives through those boundaries.

This construction still needs tests: exact rho=0 values and gradients against
hard60, exhaustive tiny-sequence enumeration, normalized transitions, visibility
loss/reset, clutter interruption, numerical scaling, actual RF/channel/gap reset,
and finite differences for physical and clock parameters away from mask changes.
It does not justify a chosen rho, verified track identity, predictive improvement,
or better geographic accuracy. No recording-dependent parameter or reference
coordinate enters this derivation.
