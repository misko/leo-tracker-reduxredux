import numpy as np

from report_ds23_dbg01_iteration_002 import native_runs


def test_native_orbit_display_breaks_at_alias_wrap_and_long_time_gap():
    times=np.array([0.,1.,2.,3.,20.])
    canonical=np.array([100.,101.,102.,103.,104.])
    native=canonical+np.array([0.,0.,1.,1.,1.])/4.4e-6
    runs=native_runs(times,native,canonical)
    assert [r.tolist() for r in runs]==[[0,1],[2,3],[4]]
