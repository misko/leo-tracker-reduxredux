# Normalized low-rank stay/reset HMM component

This is a pure synthetic component, not a qualified population orbit model or localization experiment. No observation preparation, propagation, candidate selection, timing quadrature, model adapter, corpus scoring or fitting occurs here. A three- or five-node timing quadrature remains a separate scientific gate.

`kernel.evaluate(log_emission, reset_log_weight, stay_probability, observedmask)` accepts three arrays of shape `[N,K]` and a boolean mask `[N]`, with nonempty dimensions. It returns `HMMTerms` containing `nll`, `log_normalizers[N]`, smoothed `posterior[N,K]` and NLL gradients `log_emission_gradient`, `reset_log_weight_gradient`, `stay_probability_gradient`, all `[N,K]`.

Each reset distribution is the row softmax of its log weights. The initial distribution is `pi[0]`; initial stay probabilities are unused with zero gradient. For later metadata rows the transition is

`T[n,i,j] = s[n,i] * 1(i=j) + (1-s[n,i]) * pi[n,j]`.

Normalized emission distributions are supplied externally. This component does not infer their units or normalization, choose observations, transform visibility, interpret satellite identities, or enforce a timing prior. Missing rows use emission one, with exactly zero input-emission gradient. They retain their transitions and can have nonzero reset/stay gradients because future observed rows carry information through them. All-missing data have exactly zero NLL and gradients, and their posterior is the forward state distribution.

Forward and backward recurrences use log-domain vectors and the diagonal-plus-reset rank-one structure. Work and storage are O(NK), with no K×K transition matrix. Backward common-scale normalization is a numerical gauge. Reset gradients include both destination counts and the row-softmax normalizer. Stay gradients use signed log differences after including the previous filtered log mass, avoiding an underflowed zero multiplied by an overflowing adjoint. Posterior means the state distribution given **all observed rows**; it is not a causal filtering output.

Finite log inputs and `-inf` inactive entries are supported. Each reset row needs at least one active state and the observed sequence must have viable likelihood. Observed NaN/positive-infinity emissions are rejected; missing emission inputs are never consumed, including NaN placeholders. Stay probabilities include zero and one. Inactive reset weights do not prohibit a state reached through a stay transition.

Reset weights and observed emissions are centered by row maxima, and forward log vectors are centered before log-sum-exp. This is necessary: the initial draft's `weights-logsumexp(weights)` lost the small normalization term under a huge common offset, producing mass two for two equal states. Independent review caught that bug before sealing; the draft was never used on data. The corrected tests cover common offsets of magnitude `1e100`, normalized posteriors and all three derivative fields.

This implementation does not promise arbitrary finite float64 dynamic range. Finite internal centered log values must have floating-point spacing no larger than `2^-20` (about `9.54e-7` log units), supporting magnitudes through approximately `8.6e9`. This exceeds a synthetic 4,000-row accumulation of per-row contrasts around `4e5`; it is a numerical range guard, not a corpus qualification or guarantee about future chain-rule gradients. Larger contrasts fail closed. A supported `1.6e9` cancellation fixture retains normalized posterior and gradients; `1e100` contrasts are rejected. Huge **common** offsets are removed and supported, but returned absolute float64 NLL and log normalizers necessarily have coarse ULP precision at those scales. Genuine derivative or logarithmic overflow raises rather than clipping to a finite value or silently returning NaNs. Underflow of unrepresentably small probabilities or derivatives is allowed.

Eighteen owned tests cover explicit latent-path/transition enumeration; normalized discrete emissions with and without missing rows; all three interior derivative fields; row-softmax gauge invariance; no-information all-missing data; missing-input invariance; exact independent-mixture nesting at zero stay; inactive states; one-sided zero/one stay derivatives; a long tiny-density sequence; state permutations; an underflowed-state rescue; genuine overflow rejection; one state/one row; input immutability; common-offset regressions; unsupported range rejection; cloned-state posterior/shared-gradient invariance; and normalized single-missing-point prediction matching the TRAIN-smoothed posterior mixture. The latter is a synthetic conditional-density identity, not an implemented held-data scoring policy or permission to multiply correlated singleton forecasts.

No model parameter, satellite, window, reference position, RF observation or held measurement was selected or tuned by these tests. Any future adapter must separately qualify emission normalization, transition/reset metadata semantics, chain-rule gradients, masks, priors, timing integration, and predictive conditioning before fitting.

Reproduce the owned suite with pytest (these are pytest functions; unittest discovery does not collect them):

```bash
sudo -n env PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python -m pytest -q \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_17_dsx01_iteration10/population_hmm_kernel/test_kernel.py
```

The owned run passed all 18 cases in 0.75 seconds. Independent B and root runs also passed all 18 cases (0.64 and 0.90 seconds respectively). Ruff passed. These are synthetic component tests, not a performance campaign. The separately investigated population timing quadrature remains unqualified; this kernel seal does not override that negative result or authorize any coarse-node model fit.
