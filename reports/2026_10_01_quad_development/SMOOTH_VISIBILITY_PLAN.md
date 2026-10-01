# Smooth visibility: mathematical prototype and integration gates

The [fixed-state diagnostic](GRADIENT_DIAGNOSIS.md) identifies a hard visibility-count jump in the background score. A separate mathematical prototype now computes normalized, differentiable association weights. It has not been connected to any benchmark scorer or optimizer.

Let \(m_{it}(x)\) be candidate \(i\)'s elevation margin at observation \(t\), and \(w>0\) a width in degrees. The prototype uses

\[
v_i(x)=\prod_t\sigma(m_{it}(x)/w),\quad
\pi_i(x)=\frac{p_s}{N}v_i(x),\quad
\pi_b(x)=1-\frac{p_s}{N}\sum_i v_i(x).
\]

Signal and background weights sum to one. Their derivatives are

\[
\nabla\log v_i=\sum_t\frac{1-\sigma(m_{it}/w)}{w}\nabla m_{it},\qquad
\nabla\log\pi_b=-\frac{p_s}{N\pi_b}\sum_i v_i\nabla\log v_i.
\]

Stable log-sigmoid arithmetic avoids underflow in signal log weights. Seven tests verify normalization, every signal/background derivative against finite differences, zero derivative of total mass, extreme margins and invalid parameter rejection. These are mathematical consistency tests, not localization results.

The product of gates is a modeling assumption, not a measured visibility probability. It depends on observation count and may overweight many nearly duplicate samples. Before adopting it, compare it with a shared-threshold or smooth worst-margin model and include observation-count sensitivity. Width must not be chosen solely to rescue the rejected pair. Candidate residual likelihood, physically occulted signals, background mass and the original horizon margin need consistent treatment.

The current fast solver forms derivatives from selected-satellite residuals and Gaussian nuisance priors; background contributes no derivative. Therefore changing only the branch scores would be incorrect. A separate solver/port extension must include the new association-weight gradient for signal and background branches and use a descent safeguard with the same full objective. Acquisition, selected-branch scoring, assignment selection and the independent finite-difference audit must agree. Preserve the original solver and public contracts; introduce the experimental behavior through a narrow new interface.

First verify geometry-margin derivatives on synthetic cases and real prepared tracks, then verify the complete objective gradient at ordinary points and across the diagnosed boundary. Test all-background tracks and candidate support explicitly. Only after those gates should a fixed pilot compare smooth weights with the baseline under identical starting states, parameter priors and budgets. A later full-panel test must retain failures and separate initialization, visibility-model and runtime changes. No current pair or quad result is relabeled by this prototype.
