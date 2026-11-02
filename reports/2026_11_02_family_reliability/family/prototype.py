"""Report-local family covariance sensitivity; frozen ALGO07 numerical engine."""
import copy
from pathlib import Path
import numpy as np
from algo07_science import engine as e
from probe_ds23_history_calibrated_phase import make_problem

ROOT = Path(__file__).resolve().parent
INPUT = Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_01_ds26_ds27_causal_variants')
SCALES = (1., 2., 4.)


def configure(input_root=INPUT, output_root=ROOT):
    e.configure(input_root, output_root)
    e.ROOTS['DS26'] = Path(input_root)


def select_family(d, z):
    """Select the first generic ALGO07 RF influence-triggered family."""
    ranked, eligible = e.rank_families(d, z)
    if not eligible:
        raise ValueError('No family passes existing RF influence trigger')
    return eligible[0], ranked


def scaled_mode_bank(bank, local, scale):
    """Scale existing physical SD directions; never mutate shared cached arrays."""
    if not np.isfinite(scale) or scale < 1:
        raise ValueError('Finite physical SD scale >=1 required')
    result = dict(bank)
    for key in ('position_km', 'velocity_km_s'):
        result[key] = np.asarray(bank[key]).copy()
        result[key][3*local:3*local+3] *= scale
    return result


def candidate_context(d, z, scale, family=None):
    """Return a context usable by e.build, previous.fit, and predictive callers.

    The only change is the three existing Gaussian physical SD directions for
    one RF-selected satellite. Receiver priors, phase priors, masks, aliases,
    fragment constants, noise powers, and all observations are retained.
    """
    if scale not in SCALES:
        raise ValueError('Scale outside frozen grid')
    if family is None:
        family, _ = select_family(d, z)
    original = d.get('problem_factory', make_problem)

    def factory(scan, node, keep, arm, reference, powers, means, multiplier, nu):
        p = original(scan, node, keep, arm, reference, powers, means, multiplier, nu)
        j = next((j for j in p.labels if int(scan.norads[j]) == family), None)
        if j is None or j not in p.supported:
            raise ValueError('Selected family lacks existing physical modes')
        p.mode_bank = scaled_mode_bank(p.mode_bank, p.labels.index(j), scale)
        p.mode_metadata = copy.deepcopy(p.mode_metadata)
        p.mode_metadata[j]['report_physical_SD_scale'] = scale
        p.family_discrepancy = dict(norad=int(family), SD_scale=scale,
                                    covariance_scale=scale**2, added_columns=0)
        return p

    dd = dict(d, problem_factory=factory, problems=dict(d['problems']))
    dd['family_discrepancy'] = dict(norad=int(family), SD_scale=scale,
                                  covariance_scale=scale**2, added_columns=0)
    return dd


def build_candidate(d, z, arm, reference, scale, family=None):
    dd = candidate_context(d, z, scale, family)
    return e.build(dd, z, arm, reference)
