"""Response-masked local receiver contrast for the existing Hz/GHz RF term."""
from pathlib import Path
import sys
import numpy as np

SCORE_SOURCE = Path(__file__).resolve().parents[1]/'band_drift_diagnosis'
sys.path.insert(0, str(SCORE_SOURCE))
from score import mixture_score, profile_frequency_score

PARAMETER_SCALE_HZ_PER_GHZ = 1000.


def contrast_basis(existing_rf_column, receiver):
    rf, rx = np.asarray(existing_rf_column, float), np.asarray(receiver)
    if rf.shape != rx.shape or rf.ndim != 1 or not np.isfinite(rf).all() or not set(rx) <= {0, 1}:
        raise ValueError('Finite aligned original RF column and declared receiver0/1 required')
    return (rf*np.where(rx == 0, 1., -1.))[:, None]


def masked_contrast_score(measured, prediction, visibility, sigma, q, score, rf_column, receiver, mask):
    from leo.analysis.shared_scan_model import density
    mask = np.asarray(mask, bool)
    basis = contrast_basis(np.asarray(rf_column)[mask], np.asarray(receiver)[mask])
    sigma = np.broadcast_to(np.asarray(sigma), (len(mask),))[mask]
    terms, _ = density(np.asarray(measured)[mask], np.asarray(prediction)[mask],
        np.asarray(visibility)[mask], sigma, q, score)
    return mixture_score(terms.responsibilities, terms.residual_hz, sigma, basis)


def normalized(result):
    g = float(np.asarray(result['gradient'])[0])
    information = float(np.asarray(result['complete_gaussian_information'])[0, 0])
    return dict(result, gradient_native_units=g,
        positive_information_native_units=information,
        gradient_at_1000_hz_per_ghz_scale=g*PARAMETER_SCALE_HZ_PER_GHZ,
        information_at_1000_hz_per_ghz_scale=information*PARAMETER_SCALE_HZ_PER_GHZ**2,
        signed_gradient_over_sqrt_complete_information=g/np.sqrt(information) if information > 0 else None)
