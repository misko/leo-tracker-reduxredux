"""Frequency-only geometry for catalogue proposals, without unused derivatives.

This is restricted to the recovery screen: the fitted likelihood and its
physical phase derivatives continue to use the original scientific functions.
"""

from dataclasses import dataclass
import numpy as np

from leo.analysis.research.orbit_phase_geometry import phase_shifted_states
from leo.analysis.research.track_catalogue_geometry import PreparedGeometry,prepared_frequency


@dataclass(frozen=True)
class ScreenGeometry:
    geometry: PreparedGeometry


def prepare_screen_geometry(bank,times,phases=0.):
    position,velocity=phase_shifted_states(bank,times,phases)
    norm=np.einsum('snj,snj->sn',position,position)
    product=np.einsum('snj,snj->sn',position,velocity)
    for value in (position,velocity,norm,product):value.setflags(write=False)
    return ScreenGeometry(PreparedGeometry(position,velocity,norm,product))


def screen_frequency(grid,latitude_deg,longitude_deg,*,altitude_m=0.,rf_hz=11.5e9):
    f,e=prepared_frequency(grid.geometry,latitude_deg,longitude_deg,altitude_m=altitude_m,rf_hz=rf_hz)
    # The legacy screen unpacks three slots but never reads the derivative.
    # None prevents accidentally interpreting a dummy zero as a real derivative.
    return f,e,None


def install_for_screening(screen_module):
    """Only replace this isolated experiment module's two proposal bindings."""
    screen_module.prepare_phase_geometry=prepare_screen_geometry
    screen_module.phase_linear_frequency=screen_frequency
