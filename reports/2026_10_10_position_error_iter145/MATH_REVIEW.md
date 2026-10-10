# Conditional same-component covariance: independent derivation

This proposed model changes frequency emissions, not the satellite transition prior tested in iteration 110. It is a new exploratory hypothesis, not a correlation estimate from iteration 139.

Let residuals be measured minus predicted frequency, sigma the existing frequency scale, `a=q/(1-q)`, and `u=lambda/L`. Set `s_ik=a*v_ik*phi_sigma(r_ik)` and `T_i=u+sum_k s_ik`. The unchanged singleton-event factor is `A_i=p0_i/(1-p0_i)`. For each disjoint pair, replace only the same-satellite emission product:

```
B_k = a²*v_ik*v_jk*phi_rho(r_ik,r_jk)
O_i,k = s_ik*(u + sum_{l != k} s_jl)
D = u*T_j + sum_k O_i,k + sum_k B_k
pair density = A_i*A_j*D
```

Exclusive positive prefix/suffix sums compute the off-diagonal sums in O(K). They avoid subtracting nearly equal `T_i*T_j` and diagonal sums. The implemented kernel scales each row by its singleton total before multiplication: `si=s_i/T_i`, `ui=u/T_i`, and the shared Gaussian is evaluated in log scale divided by `T_i*T_j`. Thus the positive ratio `R=D/(T_i*T_j)` changes NLL by `-log(R)` without squaring tiny clutter. Invisible shared components are omitted before exponentiation, avoiding `0*infinity`. No arbitrary likelihood floor is introduced. This construction retains clutter/clutter, clutter/signal and different-label components. Integrating over both frequencies gives the original product singleton-event mass. Dividing by `(lambda+a*sum v_i)*(lambda+a*sum v_j)` gives a normalized frequency density; the singleton mass itself must not be dropped.

Row-i satellite responsibilities are `(O_i,k+B_k)/D`; its clutter responsibility is `u*T_j/D`. Row-j uses the symmetric formula. Each row marginal sums to one, including clutter. The same-component joint mass is `B_k/D`; it is not the product of the updated row marginals.

Holding visibility and winding integers fixed, the negative-log-density derivative with respect to predicted frequency for row i/component k is:

```
g_i,k = -[O_i,k*r_ik/sigma²
           + B_k*(r_ik-rho*r_jk)/(sigma²*(1-rho²))]/D
```

This sign follows `r=measured-predicted`. The row-j expression swaps i and j. Parameter gradients contract these component derivatives with the existing prediction Jacobian. The event factors remain unchanged; their existing piecewise visibility convention remains a separate limitation. The Gaussian determinant `sqrt(1-rho²)` is essential. There are no new fitted coefficients.

At rho=0, dispatch directly to ordinary B7 score, gradients and responsibilities to preserve numerical parity. At nonzero rho, require pair-order symmetry, responsibility normalization, finite-difference gradient agreement and rho=0 parity tests. Preserve all unpaired rows exactly once.

A nearest-wrap bivariate Gaussian is only a narrow-line approximation to a normalized density on the frequency torus. Exact normalization requires a double winding sum. The kernel admits only sigma=125 Hz, positive clutter and `0<=rho<=0.25`. Any omitted image has at least one coordinate of magnitude `L/2`; the covariance's largest eigenvalue is `sigma²*(1+rho)`. In this narrow regime, a conservative lattice-tail bound is:

```
log E <= log(16) - L²/(8*sigma²*(1+rho))
                  - log(2*pi*sigma²*sqrt(1-rho²))
log relative omitted density <= log E + log K + 2*log(a) - 2*log(u)
```

The kernel requires the latter bound to be at most -700, using the physical clutter/clutter density as its lower bound. Consequently exact seams are not automatically unsupported: the ambiguous images are negligible relative to clutter in the admitted regime. This is a quantified approximation, not exact global toroidal normalization. Pair covariance is conditional on the same satellite label, not general receiver oscillator covariance across different satellites.

Iteration 139 does not calibrate rho: its fitted-c centered total was 91.68% block-mean disagreement, amplified by tiny responsibility tails. Existing full-data clock/timing fitting can also absorb covariance or induce residual dependence. Any position comparison is a consumed-data experiment, not independent confirmation of physical correlation.
