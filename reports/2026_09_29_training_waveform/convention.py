"""Remove the deterministic symbol phase from pilot-center upconversion."""

import numpy as np


def remove_upconversion_phase(symbols, center_hz):
    phase = np.exp(-2j * np.pi * center_hz * 4.4e-6 * np.arange(300))
    return symbols * phase[:, None]
