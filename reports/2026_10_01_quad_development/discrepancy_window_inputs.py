"""Reconstruct the two fixed discrepancy-pilot arms."""
import numpy as np
from run_window import prepare_window
from scan_discrepancy_ports import augment_window


def prepare_discrepancy_window(unit,arm):
    prepared=prepare_window(unit)
    if arm=='baseline':return prepared
    if arm!='sigma1':raise ValueError('Unknown discrepancy arm')
    precision,ports=augment_window(prepared,1.)
    return (*prepared[:3],precision,ports)


def initial_state(original,arm):
    state=np.asarray(original['best']['mean'],dtype=float)
    if arm=='baseline':return state.copy()
    if arm!='sigma1':raise ValueError('Unknown discrepancy arm')
    return np.r_[state,np.zeros(2*original['binding']['size'])]
