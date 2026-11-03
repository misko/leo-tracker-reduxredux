import json
import numpy as np
from plot_linear_quadratic_ratio import SOURCE, linear_quadratic_rows


def test_saved_track_ratios_reproduce_and_rank_curvature():
    rows=linear_quadratic_rows(json.loads(SOURCE.read_text()))
    assert len(rows)==22
    assert all(r['ratio']>=1 for r in rows)
    top=max(rows,key=lambda r:r['ratio'])
    assert (top['scan'],top['catalog_number'],top['receiver'])==('A',68299,0)
    assert np.isclose(top['ratio'],top['fit_plus_linear_rms_hz']/top['fit_plus_quadratic_rms_hz'])
    near_linear=next(r for r in rows if r['scan']=='A' and r['catalog_number']==64361)
    assert near_linear['ratio']<1.01
