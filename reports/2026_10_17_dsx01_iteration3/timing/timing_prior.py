"""Copy-only relative-timing prior sensitivity; no production model changes."""
from copy import copy
from dataclasses import replace

import numpy as np


def prior_context(context, relative_sigma_s, *, fixed_c=False):
    """Preserve observations, bank, bounds and other priors without cache mutation.

    SharedScanObjective reads its own score during both likelihood and gradient
    evaluation. The copied model gets an explicit score rather than changing the
    delegated raw model or any globally cached context.
    """
    width = float(relative_sigma_s)
    if not np.isfinite(width) or width <= 0:
        raise ValueError('A finite positive relative timing width is required')
    if context.model.score.common_sigma_s != 3.:
        raise ValueError('This controlled sensitivity requires the saved 3 s common prior')
    score = replace(context.model.score, relative_sigma_s=width)
    model = copy(context.model)
    model.score = score
    if context.full_model is context.model:
        full_model = model
    else:
        full_model = copy(context.full_model)
        full_model.score = score
    vector, nuisance = context.vector.copy(), context.nuisance.copy()
    if fixed_c:
        vector[6] = 0.
    return replace(context, model=model, full_model=full_model,
                   vector=vector, nuisance=nuisance, fixed_c=bool(fixed_c))


def timing_penalty(tau, common_sigma_s=3., relative_sigma_s=2.):
    tau = np.asarray(tau, float)
    common = tau.mean()
    return float(.5*(common/common_sigma_s)**2 +
                 .5*np.sum(((tau-common)/relative_sigma_s)**2))
