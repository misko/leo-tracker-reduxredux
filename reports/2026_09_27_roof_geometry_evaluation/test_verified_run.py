import importlib.util
from pathlib import Path
import numpy as np
from types import SimpleNamespace as NS
P=Path(__file__).with_name('verified_run.py');s=importlib.util.spec_from_file_location('v',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def test_completeness_selection_excludes_both_splits():
 i=[{'session_id':'c1','split':'calibration','analysis_ready':True},{'session_id':'c2','split':'calibration','analysis_ready':False},{'session_id':'h1','split':'holdout','analysis_ready':True},{'session_id':'h2','split':'holdout','analysis_ready':False}]
 assert m.complete_sets(i)==({'c1'},{'h1'})
def test_no_holdout_leakage_in_baseline():
 rows=[{'session':'c','channel':1,'rx':{0:{'detected':False},1:{'detected':False}}},{'session':'h','channel':1,'rx':{0:{'detected':True},1:{'detected':True}}}]
 assert m.baseline(rows,{'c'})[(1,0)]==.25
def test_control_separation_is_real():
 for n in (200,201,500):
  p=m.separated_shift(n); assert np.all(np.minimum((p-np.arange(n))%n,(np.arange(n)-p)%n)>=100)
 assert m.separated_shift(199) is None
def test_epoch_compatibility_wraps_modulo_frame():
 rate=7500000;c0=NS(integer_epoch_sample=10,fractional_epoch_offset_samples=0.,fractional_tracking_cfo_hz=100.);c1=NS(integer_epoch_sample=10010,fractional_epoch_offset_samples=0.,fractional_tracking_cfo_hz=200.)
 r={'rx':{0:{'candidates':[c0],'rate':rate},1:{'candidates':[c1],'rate':rate}}}
 assert m.edges(r,100.)
def test_receiver_swap_reverses_cfo_bias():
 rate=7500000;c0=NS(integer_epoch_sample=10,fractional_epoch_offset_samples=0.,fractional_tracking_cfo_hz=100.);c1=NS(integer_epoch_sample=10,fractional_epoch_offset_samples=0.,fractional_tracking_cfo_hz=4100.)
 r={'rx':{0:{'candidates':[c0],'rate':rate},1:{'candidates':[c1],'rate':rate}}}; swapped={'rx':{0:r['rx'][1],1:r['rx'][0]}}
 assert m.edges(r,4000.) and m.edges(swapped,-4000.)
