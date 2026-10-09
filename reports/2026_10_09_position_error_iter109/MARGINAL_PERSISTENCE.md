# Marginal-preserving identity persistence

This derivation concerns the categorical prior transition only. It introduces no
recording fit, selected rho, physical association claim or position result.

Let p and q be the normalized nonnegative previous and current row priors over
the same satellite bank plus clutter. For each satellite with p_i>0, define
`s_i = rho * min(1, q_i/p_i)`; clutter has s_i=0. Set s_i=0 for p_i=0
and for currently invisible satellites. Let `h_i = s_i*p_i`,
`Z = 1-sum(h)` and `r=(q-h)/Z`. For 0≤rho<1, use
`T_ij = s_i*I_ij + (1-s_i)*r_j`.

Because 0≤h_i≤rho*q_i and h_i≤rho*p_i, Z≥1-rho>0,
q-h is nonnegative and sums to Z. Thus r is a probability vector and every
row of T is normalized and nonnegative. Furthermore,

`(p T)_j = p_j*s_j + (1-sum_i p_i*s_i)*r_j = h_j+Z*r_j = q_j`.

This preserves the specified row marginals even when visibility changes.
Newly visible states have p_i=0, h_i=0 and are reached through redraw. States
losing visibility have q_i=0, s_i=0 and receive zero probability. A state absent
in both rows is harmless. Clutter remains reset on every transition while its
prescribed marginal probability is preserved by the adjusted redraw distribution.
For p=q, r_i=p_i*(1-s_i)/Z; retaining r=p instead would recreate the
nonstationary clutter bias identified in the earlier kernel.

At rho=0, s=h=0, Z=1 and r=q, so every transition redraws from the
current independent mixture. Reset rows must likewise begin directly at q.
If all mass is clutter, s=h=0 regardless of rho and the transition is the
independent limit. Rho=1 is excluded: Z can become zero when all mass is in
unchanging satellite states. Numerical normalization and finite-input assertions
remain necessary; clipping negative probabilities silently would change the model.

## Linear-cost inference

For filtered previous occupancy a, the predictive distribution is
`b = s*a + (1-dot(s,a))*r`. This costs O(K) and retains posterior persistence;
the proof pT=q does not imply aT=q for a changed by measurements. In a backward
step with emission/backward product v, use
`T v = s*v + (1-s)*dot(r,v)`. These paired recurrences avoid dense matrices
and permit the same normalized forward/backward sequence calculation as the
original kernel. Emission derivatives remain occupancy-weighted, conditional on
fixed visibility/priors and fixed transitions during those derivatives.

The construction does not eliminate inference dependencies: q depends on
candidate visibility and the fixed detection/clutter policy. As in B7, visibility
derivatives are discontinuous and held fixed in the ordinary frequency gradient.
Any future differentiable prior or continuous geometry-dependent transition
would require derivatives of T; occupancy-weighted emission gradients alone
would then be incomplete.

## Scope and test requirements

Rho specifies a retained diagonal contribution, not the total probability of
repeating a label (redraw can return the same state), not residual correlation,
and not a physical correlation time. The maximal retained mass is reduced for
states whose prior probability decreases. Time-varying priors therefore alter
effective retention without introducing an additional parameter. Even with
preserved marginals, the joint sequence prior changes; persistence requires
separate predictive and localization validation.

Synthetic tests should independently construct dense T and verify row sums,
nonnegativity, pT=q, sparse-changing visibility, all-clutter and disjoint support,
rho=0 exact nesting, receiver/segment resets, forward/backward agreement and
finite-difference emission gradients. Include near-one rho and very small
nonzero p: compute retained mass as `rho*min(p,q)` before dividing to obtain s
to avoid overflow in q/p, and verify r normalization without silent repair.
Uniformly scaled roundoff tolerances should be declared before recording work.

No rho value or downstream operational selection rule is proposed here. A future
study must keep c arms, observations, banks, starts, priors and budgets matched.
