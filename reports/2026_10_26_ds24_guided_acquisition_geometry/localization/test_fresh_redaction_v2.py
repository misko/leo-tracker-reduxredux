"""Correct serialization comparison in the archived supplementary test."""
import importlib.util
import json
from pathlib import Path
import numpy as np

spec=importlib.util.spec_from_file_location('r03_fresh_redaction_v2',Path(__file__).with_name('run.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_fresh_instances_and_trajectory_redact_held_responses():
    d=m.c.context(m.CASE)
    prior=m.c.load(m.OLD/'matched/protocol.json')['cases'][m.CASE]
    masks,held,_=m.nominate(d,prior)
    train=dict(d,keep=masks['overlap'],entries=[])
    a=m.c.frozen.build(train,'c0',np.zeros(len(d['means'])),prior['packets']['c0'])
    b=m.c.frozen.build(train,'c0',np.zeros(len(d['means'])),prior['packets']['c0'])
    b.values=b.values.copy();b.values[held]+=123456.
    for x in (np.zeros(2),np.array([.3,-.2])):
        aa=a.calculate(x);bb=b.calculate(x)
        np.testing.assert_array_equal(aa['coefficient'],bb['coefficient'])
        np.testing.assert_array_equal(aa['residual'],bb['residual'])
        np.testing.assert_allclose(bb['conditional_residual_hz'][held]-aa['conditional_residual_hz'][held],123456.,atol=1e-7)
    fa=m.c.fit(a,np.zeros(2),iterations=8);fb=m.c.fit(b,np.zeros(2),iterations=8)
    assert json.dumps(fa,sort_keys=True,default=m.c.encode)==json.dumps(fb,sort_keys=True,default=m.c.encode)
