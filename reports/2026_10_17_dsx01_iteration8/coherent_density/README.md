# Normalized coherent-group density component

This research-only component evaluates an exact shared-identity group mixture with a uniform alternative for every point. It contains no track extraction, satellite IDs, geometry, station reference, fitting, filesystem adapter or production changes. The inherited constants are fixed at `eta=.10`, `epsilon=.12`, `sigma_hz=125` and `alias_hz=1/4.4e-6`; none was selected using DSX01 windows or outcomes. Nine component tests pass. No corpus fit or recovery claim is made.

## Density and normalization

For a supplied exhaustive partition of rows into disjoint groups, let `U=1/alias_hz`, `a=1-epsilon`, `p_s=q_s/sum(q)` and `phi_ns` be the normalized wrapped-normal density of measured minus predicted CFO. The component evaluates

```text
h_ns = a*w_ns*phi_ns + (1-a*w_ns)*U
f_g  = eta*U**n_g + (1-eta)*sum_s p_s*product_{n in g} h_ns
NLL  = -sum_g log(f_g)
```

Each `h_ns` integrates to one on one alias interval, including `w=0` and `w=1`. Each product integrates to one on its group's torus; the outer mixing weights sum to one. This proves normalization **conditional on the fixed partition, visibility and predictions**. A fully invisible group is uniform, while its latent identity posterior can still equal the prior: identity weight is not evidence that a row contains signal.

For a singleton, the density is this model's own normalized point counterpart:

```text
f_n = eta*U + (1-eta)*sum_s p_s*[a*w_ns*phi_ns + (1-a*w_ns)*U]
```

It does not nest the deployed independent shared-scan density. Its normalization, foreground-mass interpretation and q scale gauge differ. An old-model/new-model likelihood comparison must state that distinction.

The wrapped normal uses an image sum in log space, retaining the largest width's approximately 8.6-sigma tails. This gives floating-point tail precision for the normalized periodic density and its derivative, including broad widths and the alias seam. It is not a nearest-image Gaussian. Group products and outer mixtures also remain in log space; the 3,000-row stress case does not underflow.

## API

Import [kernel.py](kernel.py) from this directory:

```python
terms = coherent_terms(
    measured_hz,       # [N]
    prediction_hz,     # [N,K]
    visibility,        # [N,K], finite in [0,1]
    detection_q,       # [K], strictly positive; need not sum to one
    group_labels,      # [N], one finite/nonmissing hashable scalar per row
    sigma_hz=125.,     # scalar, [N], or broadcastable [N,K]
    alias_hz=1/4.4e-6,
    eta=.10,
    epsilon=.12,
)
```

All rows must be provided exactly once through the labels vector. Noncontiguous rows may share a group. Label renaming and row ordering do not change total NLL. Returned group order follows first occurrence; `group_index[N]` maps rows to groups and `group_labels[G]` is a tuple. Malformed shapes, missing labels, out-of-range visibility, nonpositive widths/q and invalid density floors raise `ValueError`. Both `eta` and `epsilon` must lie strictly between zero and one.

`CoherentTerms` provides:

| Field | Meaning |
|---|---|
| `nll` | Total negative log density, without any prior |
| `group_nll[G]` | Additive group NLL; there is no independent row NLL |
| `group_posterior[G,K+1]` | Column 0 all-clutter group; columns 1..K candidate branches |
| `signal_responsibility[N,K]` | Effective probability that the row is signal from that candidate |
| `responsibilities` | Alias for `signal_responsibility` for narrow adapter compatibility |
| `clutter_probability[N]` | All-clutter group plus candidate branches choosing uniform for this row |
| `residual_hz[N,K]` | Circular measured-minus-predicted residual |
| `prediction_gradient[N,K]` | Derivative of total NLL with respect to predicted Hz |
| `visibility_gradient[N,K]` | Derivative of total NLL with respect to visibility, including endpoints |
| `q_gradient[K]` | Derivative of total NLL with respect to input q before normalization |

With `gamma_gs` denoting candidate group posterior and `rho_ns=a*w_ns*phi_ns/h_ns`, effective signal responsibility is `gamma_gs*rho_ns`. Consequently row signal probabilities plus row clutter probability sum to one. Group identity posterior alone must not be used as row signal responsibility.

The derivatives used by the adapter are

```text
dNLL/dpred_ns = -gamma_gs*rho_ns * dlog(phi_ns)/dpred_ns
dNLL/dw_ns    = -gamma_gs*a*(phi_ns-U)/h_ns
dNLL/dq_s     = sum_g [(sum_j gamma_gj)/sum(q) - gamma_gs/q_s]
```

`dlog(phi)/dpred` uses the weighted signed wrapped-image residual divided by sigma squared. Its sign matches the public prediction-gradient convention. Visibility's formula remains finite at zero without dividing by visibility. The q derivative includes normalization once per group, not once per row. Rescaling all q leaves the density unchanged, rescales its gradient inversely, and obeys `dot(q,q_gradient)=0`. Positive q is an explicit interior-domain contract; a caller with exact zero q must choose a declared parameterization rather than silently clipping it here. Any calibration, physical, timing, visibility-chain or prior derivatives belong to the adapter; this kernel adds no priors.

## Qualification and limits

If automatic grouping is selected from measured training CFO, evaluation of `f(y | selected partition)` omits the probability of that selection. This component therefore does not establish an unconditional generative density or a Bayes factor across different grouping procedures. A fixed generic grouper can be studied as a declared research assumption, with its selection limitation explicit. Training-only grouping and genuinely excluded held CFO remain the adapter/harness's responsibility: this kernel only sees the rows passed to it.

The model assumes conditional independence of rows given the group identity and the per-row signal/uniform choices. It does not establish emitter identity, a detection-count process, transmitter continuity, visibility truth or a physical cause of residuals. Overlapping emitters, multiple lines in one extracted group and crossings can violate the shared-identity assumption. Point clutter and the all-clutter branch retain those alternatives but do not guarantee correct grouping. A singleton held predictive score is the marginal new-model counterpart, not the training group objective. No fitted-c versus c-zero performance conclusion follows from these component tests.

## Verification

[test_kernel.py](test_kernel.py) contains nine hardware-free tests:

- Independent enumeration of both identities and every point-clutter allocation for a two-row group.
- Numerical normalization on the one-dimensional alias circle and a two-dimensional group torus.
- Independent singleton closed-form density and effective responsibilities.
- Central finite differences for prediction, visibility and q, including q normalization and its scale gauge.
- Fully invisible groups, fully visible boundaries, and one-sided endpoint visibility derivatives.
- Alias shifts, seam derivatives, and a very broad wrapped-normal limit.
- Row ordering, label renaming, noncontiguous membership, singleton decomposition and posterior sums.
- A 3,000-row group with stable finite log density and gradients.
- Explicit rejection of invalid partitions, probability inputs and widths.

The executed pinned-runtime test receipt is [test-results.json](test-results.json): nine passed, zero failures/errors/skips, approximately 0.021 seconds in the unittest runner. It records the exact kernel and test source hashes. Reproduction:

```bash
sudo -n env PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/opt/leo-fast-auto/f141dbb30321bc8f9e8183576c511431ea60a6b3/worker/src \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python \
  -m unittest discover -s reports/2026_10_17_dsx01_iteration8/coherent_density -p 'test_*.py' -v
```

Only NumPy and SciPy are runtime dependencies. No deployed likelihood is imported. `manifest.json` binds this component, its tests, receipt and documentation; the adapter and any later pilot are separate components with their own qualification and receipts.
