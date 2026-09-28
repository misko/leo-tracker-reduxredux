import importlib.util,sys
from pathlib import Path
import pytest
P=Path(__file__).with_name('calibrate_frequency_fixedpoint.py');s=importlib.util.spec_from_file_location('fp',P);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
def test_convergence_requires_both_parameters_and_maps():
 assert m.convergence((100,2),(100.5,2.01),{'a':1},{'a':1})['converged']
 assert not m.convergence((100,2),(102,2.01),{'a':1},{'a':1})['converged']
 assert not m.convergence((100,2),(100.5,2.01),{'a':1},{'a':2})['converged']
def test_relative_change_is_symmetric_enough_for_fixed_previous_denominator():
 assert m.relative_change(100,101)==pytest.approx(.01)
