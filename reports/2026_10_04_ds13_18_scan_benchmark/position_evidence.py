"""Numerical eligibility for saved local position fits; not a global certificate."""
import numpy as np


def joint_stationary_at_best(result):
    best=result['best_found']
    if best['success'] and not best['fixed_location']:return True
    return any(r['success'] and not r['fixed_location']
               and abs(r['objective']-best['objective'])<=1e-7
               and np.linalg.norm(np.asarray(r['point_km'])-best['point_km'])<=1e-4
               for r in result['records'])


def eligible(result,metadata):
    return bool(joint_stationary_at_best(result) and not result['boundary'] and not metadata.get('calibration_warnings'))
