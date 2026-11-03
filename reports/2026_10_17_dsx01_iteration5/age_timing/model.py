"""Fixed heterogeneous relative timing regularizer; unchanged data likelihood."""

import importlib.util
from pathlib import Path

import numpy as np
from leo.analysis.shared_scan_model import SharedScanObjective

PROFILE_SOURCE = Path(__file__).resolve().parents[2]/'2026_10_16_dsx01_iteration2/profile_search.py'
spec = importlib.util.spec_from_file_location('original_signed_profiles', PROFILE_SOURCE)
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


def widths(provider, ages_days, calibration):
    """Conservative sensitivity: supported historical core, fixed .5/2s floor/cap."""
    ages = np.asarray(ages_days, float)
    if not np.isfinite(ages).all():
        raise ValueError('finite signed entry ages required')
    result = np.full(ages.shape, 2.)
    statuses = np.full(ages.shape, 'unsupported-age/provider-baseline2', dtype=object)
    for entry in calibration['age_bins']:
        if (entry['provider'] != provider or entry.get('distinct_objects', 0) < 100
                or entry.get('count', 0) == 0):
            continue
        lower, upper = entry['lower_age_days'], entry['upper_age_days']
        use = (ages >= lower) & ((ages < upper) if upper is not None else True)
        result[use] = np.clip(entry['mad_sigma_s'], .5, 2.)
        statuses[use] = 'historical-core-sensitivity-floor.5-cap2'
    return result, statuses.tolist()


def timing_penalty_delta(tau, proposed, sigmas, common_sigma=3.):
    """Exact independent one-satellite changes, including every recentered delta."""
    tau, proposed, sigmas = map(lambda a: np.asarray(a, float), (tau, proposed, sigmas))
    if (tau.ndim != 1 or tau.shape != proposed.shape or tau.shape != sigmas.shape
            or len(tau) < 2 or np.any(sigmas <= 0)
            or not np.isfinite(np.r_[tau, proposed, sigmas, common_sigma]).all()
            or common_sigma <= 0):
        raise ValueError('aligned finite timings and positive fixed widths required')
    if np.all(sigmas == 2.):
        return profile.timing_penalty_delta(tau, proposed, common_sigma, 2.)
    common = tau.mean()
    relative = tau-common
    change = proposed-tau
    count = len(tau)
    weight = 1/sigmas**2
    linear = relative*weight-np.sum(relative*weight)/count
    quadratic = weight*(1-2/count)+weight.sum()/count**2
    return (.5*((common+change/count)**2-common**2)/common_sigma**2
            +change*linear+.5*change**2*quadratic)


class RelativeTimingModel(SharedScanObjective):
    def __init__(self, source, sigmas):
        if (type(source) is not SharedScanObjective or source.score.relative_sigma_s != 2.
                or source.score.common_sigma_s != 3.):
            raise ValueError('exact original shared model with2s relative/3s common prior required')
        sigmas = np.broadcast_to(np.asarray(sigmas, float), (len(source.bank.numbers),)).copy()
        if not np.isfinite(sigmas).all() or np.any(sigmas <= 0):
            raise ValueError('positive finite fixed per-object timing widths required')
        self.__dict__.update(source.__dict__)
        sigmas.flags.writeable = False
        self.relative_sigmas_s = sigmas

    def evaluate_details(self, vector, nuisance):
        result, details = super().evaluate_details(vector, nuisance)
        if np.all(self.relative_sigmas_s == 2.):
            return result, details
        relative = self.basis@np.asarray(vector)[8:]
        difference_precision = 1/self.relative_sigmas_s**2-.25
        penalty = .5*float(relative@(difference_precision*relative))
        gradient = result[1].copy()
        gradient[8:] += self.basis.T@(relative*difference_precision)
        return (result[0]+penalty, gradient, *result[2:]), dict(details,
            prior_penalty=details['prior_penalty']+penalty,
            relative_timing_sigmas_s=self.relative_sigmas_s,
            relative_timing_prior=.5*float(np.sum((relative/self.relative_sigmas_s)**2)),
            original_relative_timing_prior=.125*float(relative@relative))


class Profiles(profile.Profiles):
    """Original exact data profiles, with exact heterogeneous prior differences."""
    def score(self, times):
        score = super().score(times)
        sigmas = self.model.relative_sigmas_s
        if np.all(sigmas == 2.):
            return score
        old = profile.timing_penalty_delta(self.tau, times, self.model.score.common_sigma_s, 2.)
        new = timing_penalty_delta(self.tau, times, sigmas, self.model.score.common_sigma_s)
        return score-old+new
