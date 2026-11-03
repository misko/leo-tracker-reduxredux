# Training-only high/low band drift score

The blocked S03 training endpoint has a detectable local band-constant score,
but only modest additional high-band drift scores. After projecting existing
frequency directions and both new band constants, the two drift normalized
scores are +2.52 and −1.68. These are descriptive positive-information scores,
not p-values or proof that a drift model improves prediction. No parameters were
fit and no held measurements or saved held evaluations were opened.

## Inputs and four predeclared directions

The sealed public `blocked_cold/training_context.py::load_training_context()`
reconstructs the 2,073 TRAIN observations, their 45 training-selected satellites,
unchanged causal orbit bank, calibration and strict selected endpoint. Only
that derived training input and training receipts enter this calculation.

For each contract receiver 0/1 the added prediction is
`high * (constant_hz + drift_hz_s * (time-training_midpoint))`, shared by every
candidate at that observation. The midpoint is half the training minimum plus
maximum time. All actual receiver/channel assignments remain unchanged. No
window, satellite, position or manual track selection enters the basis.
Predeclared reporting scales are 100 Hz for constants and 1 Hz/s for drifts;
these are unit scales, not prior widths or fitted amplitudes.

## Exact all-candidate mixture derivatives

Let r_ik be wrapped residual, p_ik the existing signal responsibility, sigma_i
the unchanged noise width, and B_i the four-column design. With fixed physical
state, visibility and q, every candidate receives the same row shift. The
normalizer is unchanged. The exact data-NLL row gradient and curvature at zero
are:

```
g_i = -sum_k(p_ik*r_ik)/sigma_i^2
h_i = sum_k(p_ik)/sigma_i^2
      - sum_k(p_ik*r_ik^2)/sigma_i^4
      + (sum_k(p_ik*r_ik)/sigma_i^2)^2
gradient = B.T @ g
observed Hessian = B.T @ diag(h) @ B
```

No winner is selected. Clutter and competing assignments remain in the
responsibilities. The separately reported positive Gaussian information is
`B.T @ diag(sum_k(p_ik)/sigma_i^2) @ B`: it freezes responsibilities and omits
their allocation derivative. It is not the observed mixture Hessian, an exact
observed Fisher matrix, parameter variance or calibrated identity confidence.

| Direction | Exact data gradient | Observed diagonal curvature | Positive Gaussian information | Gradient / sqrt(information) |
|---|---:|---:|---:|---:|
| RX0 high constant, Hz | +0.69891 | 0.020155 | 0.028207 | +4.161 |
| RX0 high drift, Hz/s | +14.76388 | 182.869662 | 231.110777 | +0.971 |
| RX1 high constant, Hz | −0.04053 | 0.001458 | 0.003233 | −0.713 |
| RX1 high drift, Hz/s | −1.92917 | 8.046913 | 21.067665 | −0.420 |

Existing free receiver-intercept/shared-slope full objective gradients are
approximately `[4.67e-8, -5.80e-6, -7.90e-8, 4.17e-6]` in their native units.
Those include existing priors; new-direction gradients above are data-NLL only.
There is no prior on a new direction in this diagnostic.

RX0 high has 696 rows, 440.74 summed signal responsibilities, and 458.57 Kish
effective rows. RX1 high has 233 rows, 50.51 summed signal responsibilities and
55.16 Kish rows. Constant and drift within a lane share these rows; they are not
independent samples. There are 225/696 and 133/233 rows with negative individual
mixture curvature. The aggregate four-direction observed Hessian happens to be
positive definite at this endpoint, with eigenvalues 4.94, 17.69, 108.80, 275.62
after the stated coordinate scaling. This establishes neither global convexity
nor predictive reliability.

## Local nuisance projection

Two additional diagnostics project the new directions through the
responsibility-weighted Gaussian frequency tangent. The first includes existing
shared receiver calibration and residual-clock columns. The second also
includes physical position and all common/relative orbital timing columns.
Both use every candidate and weight p_ik/sigma_i², with no chosen-identity
regression. Columns are normalized before a fixed 1e−9 least-squares rank cutoff.
q/visibility derivatives and existing priors are omitted in this projection;
it is not a full efficient-score statistic, optimizer or likelihood-ratio test.

| Direction | Existing calibration projected | All existing frequency directions projected |
|---|---:|---:|
| RX0 high constant | +9.806 | +11.612 |
| RX0 high drift | +1.492 | +1.489 |
| RX1 high constant | −0.642 | −0.669 |
| RX1 high drift | −1.251 | −1.323 |

These columns still correlate with one another. A Schur projection additionally
removes both new constant directions. Resulting drift scores are +2.968/−1.220
after existing calibration, or +2.523/−1.684 after all existing frequency
directions. The latter Gaussian-information matrix is approximately
`[[61.924, 0.099], [0.099, 4.638]]` in native drift units. It is positive local
information only; the reported score energy is not a chi-squared test.

The local score therefore supports checking the already-studied band constants
before prioritizing a new drift model. It does not rule out distant nonlinear
basins, and cannot choose drift prior widths or a model from held performance.
If a later general band-drift model is tested, use only two receiver-specific
high/low drift contrasts with a proper zero-centered prior, preserve the same
training bank/classifier/total signal normalization, include matched c=0 and
ordinary continuation, and freeze before held scoring. This diagnostic does not
implement or promote that model.

## Validation and costs

Three hardware-free synthetic tests pass: all four exact gradients and Hessian
columns match finite differences of the full all-candidate density; arbitrary
held CFO changes leave training design/score/curvature exactly invariant; and
projection removes an already-existing direction without choosing identities.

The final receipt records one explicit training objective evaluation and one
additional physical Jacobian projection, plus the public loader's replay/audits.
It also records elapsed time and hashes of code, training input, terminal and
loader. Development used three bounded training-only executions, including one
serialization retry and the final extra constant-profile calculation; none fit
parameters or opened held measurements. No RF, production writes, sealed-file
changes, new satellite hypotheses or reference-position seeds were used.
`diagnosis.json` retains the complete matrices, gradients, scales and effective
counts for independent inspection.
