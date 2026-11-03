import importlib.util
from pathlib import Path

import numpy as np

spec=importlib.util.spec_from_file_location('orbit_direction_test',Path(__file__).with_name('run.py'))
run=importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def test_direction_shape_and_offsets():
    t=np.arange(-5.,6.)
    a=run.shape(t,4*t+100,2*t+3000)
    assert abs(a['linear_fraction']-1)<1e-12 and abs(a['projection_beta']-.5)<1e-12
    b=run.shape(t,t*t,np.ones(len(t)))
    assert abs(b['linear_fraction'])<1e-12
    c=run.shape(t,np.ones(len(t)),t)
    assert c['linear_fraction'] is None and c['projection_beta'] is None
