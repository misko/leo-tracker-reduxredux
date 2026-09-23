import importlib.util
from pathlib import Path

import numpy as np


def test_regional_cap_retains_visible_boundary_directions():
    path = (Path(__file__).resolve().parents[2]
            / 'reports/2026_09_23_long_cache_feasibility/helper/export_long_training_cache.py')
    spec = importlib.util.spec_from_file_location('long_export_visibility', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    caps = module.regional_normal_caps()
    positions = []
    for _, normal, radius in caps:
        east = np.cross([0.0, 0.0, 1.0], normal)
        east /= np.linalg.norm(east)
        north = np.cross(normal, east)
        for angle in np.linspace(0, 2 * np.pi, 32):
            tangent = np.cos(angle) * east + np.sin(angle) * north
            edge_normal = np.cos(radius * .999) * normal + np.sin(radius * .999) * tangent
            horizon = np.cross(edge_normal, tangent)
            horizon /= np.linalg.norm(horizon)
            positions.append(6378.137 * edge_normal + 1500 * horizon)
    assert module.possibly_visible_in_regional_caps(np.asarray(positions)[:, None], caps).all()
    far_side = -7000 * caps[0][1]
    assert not module.possibly_visible_in_regional_caps(far_side[None, None], caps)[0]
