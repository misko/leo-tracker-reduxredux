from pathlib import Path
import sys
import importlib.util

import numpy as np
import pytest
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import extra_pass
import pipeline


def test_raw_winner_tie_and_distinct_windows():
    rows=[dict(probe_key=[1,0,0],row_index=3,margin=.2),
          dict(probe_key=[1,0,0],row_index=2,margin=.2),
          dict(probe_key=[1,1,0],row_index=4,margin=.1)]
    assert pipeline.top_indices(rows).tolist()==[1,2]


def test_additional_pass_keeps_previous_good_score():
    old=dict(status='refined',tracking_cfo_hz=100.,margin=.8,exact=.9,control=.1,epoch=10.,center_hz=100.)
    row=dict(integer_epoch_sample=10,fractional_epoch_offset_samples=0.)
    def score(f,e):return dict(tracking_cfo_hz=f,margin=.7,exact=.8,control=.1)
    chosen,audit=extra_pass.improve(score,row,dict(output_hz=100.,refinement=old))
    assert chosen==old and audit['retained_previous']


def test_additional_pass_uses_measured_start_no_orbit():
    old=dict(status='refined',tracking_cfo_hz=100.,margin=.5,exact=.6,control=.1,epoch=10.,center_hz=95.)
    row=dict(integer_epoch_sample=8,fractional_epoch_offset_samples=.25)
    calls=[]
    def score(f,e):
        calls.append((f,e));return dict(tracking_cfo_hz=f,margin=.7,exact=.8,control=.1)
    chosen,audit=extra_pass.improve(score,row,dict(output_hz=100.,refinement=old))
    assert len(calls)==13 and calls[0][1]==10.
    assert chosen['margin']==.7 and not audit['retained_previous']
    assert calls[1][0]==100.


def test_failed_extra_pass_keeps_successful_parent():
    old=dict(status='refined',tracking_cfo_hz=100.,margin=.8,exact=.9,control=.1,epoch=10.,center_hz=100.)
    row=dict(integer_epoch_sample=10,fractional_epoch_offset_samples=0.)
    def score(f,e):return dict(tracking_cfo_hz=float('nan'),margin=.9,exact=1.,control=.1)
    chosen,audit=extra_pass.improve(score,row,dict(output_hz=100.,refinement=old))
    assert chosen==old and audit['attempt_status']=='no_local_maximum'


def test_cross_stage_seed_transfer_preserves_total_receiver_line():
    spec=importlib.util.spec_from_file_location('glrt_ablation_polish',HERE/'polish.py')
    polish=importlib.util.module_from_spec(spec);spec.loader.exec_module(polish)
    old=SimpleNamespace(numbers=np.array([10,20]),group=np.array([1,2,3,4]),
        fixed_receiver_hz=np.array([100.,110.,200.,220.]))
    new=SimpleNamespace(numbers=np.array([20,30]),group=old.group,
        fixed_receiver_hz=np.zeros(4),receiver=np.array([0,0,1,1]),
        times=np.array([150.,160.,150.,160.]),initial=np.array([0.,0.,0.,0.,0.,0.,0.,7.]))
    result=polish.transfer(dict(parameters=[0.,0.,1.,2.,3.,4.,5.,6.]),old,new)['parameters']
    np.testing.assert_allclose(result,[0.,0.,101.,3.,203.,6.,6.,7.],atol=1e-10)


@pytest.mark.real_corpus
def test_raw_and_saved_inventory_matches():
    """Requires the declared local DS13 N01 materialized research corpus."""
    raw=pipeline.load_stage('N01','raw');saved=pipeline.load_stage('N01','pass1')
    assert len(raw.times)==len(saved.times)==2728
    assert set(raw.group)==set(saved.group)
    source=pipeline.original_load(pipeline.calibration.INPUTS/'N01/seed-timing-v6')
    np.testing.assert_array_equal(saved.original_rows,source.original_rows)
    np.testing.assert_array_equal(saved.measured,source.measured)
    np.testing.assert_array_equal(saved.margin,source.margin)
    assert np.array_equal(raw.numbers,saved.numbers)
