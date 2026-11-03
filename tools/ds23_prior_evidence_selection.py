"""RF-only, paired selection among independently learned causal phase priors."""

import math


def choose_prior(baseline_losses, alternatives, *, model_count=3):
    """A new prior must repay its discrete search cost in each c control.

    Losses are normalized negative-twice variational bounds on exactly the
    same measurements. This is a model-selection heuristic, not calibrated
    identity odds or a GPS-dependent accuracy selector.
    """
    arms = ('c0', 'fitted_c')
    if model_count < 1 or any(not math.isfinite(baseline_losses[a]) for a in arms):
        raise ValueError('finite matched baseline losses and a model count required')
    penalty = 2 * math.log(model_count)
    eligible, receipts = [], []
    for name, record in alternatives.items():
        losses = record['losses']
        finite = all(math.isfinite(losses[a]) for a in arms)
        gains = {a:baseline_losses[a]-losses[a] for a in arms}
        valid = bool(record['qualified_pre_RF'] and record['paired_valid'] and finite and
                     all(gains[a] > penalty for a in arms))
        receipts.append(dict(model=name, eligible=valid, RF_gains=gains,
                             penalty=penalty, qualified_pre_RF=record['qualified_pre_RF'],
                             paired_valid=record['paired_valid']))
        if valid:
            eligible.append((losses['c0'], name))
    return dict(model=min(eligible)[1] if eligible else 'original', penalty=penalty,
                alternatives=receipts, same_choice_for_both_c_arms=True)
