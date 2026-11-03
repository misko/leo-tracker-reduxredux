import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tools'))
from evaluate_cadence_schedule import evaluate


def receipts():
    rows=[{'kind':'cadence','origin_ns':100,'period_ns':100,'scans':2,'pending_capacity':1,'detector_capacity':2}]
    def start(i,det,t):return dict(kind='launch',scan=i,detector=det,monotonic_ns=t,scan_origin_ns=100+i*100,pid=10+i*2+det)
    def end(i,det,t):return dict(kind='finish',scan=i,detector=det,monotonic_ns=t,exit_code=0)
    rows.extend([start(0,True,90),start(1,True,190),end(0,True,205),start(0,False,206),end(0,False,295),end(1,True,305),start(1,False,306),end(1,False,395),
                 dict(kind='memory',monotonic_ns=396,process_tree_rss_kib=1,pending_scans=0),
                 dict(kind='summary',success=True,completed_scans=2,pending_high_water=1,detector_process_high_water=2,sampled_peak_process_tree_rss_kib=1)])
    clocks=[dict(kind='replay_clock',clock='CLOCK_MONOTONIC',external_origin=True,origin_ns=100+i*100,ready_ns=95+i*100) for i in range(2)]
    return rows,clocks


def test_complete_schedule():
    result=evaluate(*receipts(),100,2)
    assert result['fixed_cadence_and_capacity_passed']
    assert result['scans'][0]['downstream_finished_before_next_scan_ready']
    assert result['scans'][1]['downstream_finished_before_next_scan_ready'] is None


def test_changed_monitoring_policy_rejected():
    rows,clocks=receipts();rows[0]['memory_sample_ms']=1000
    with pytest.raises(ValueError,match='sampling interval'):evaluate(rows,clocks,100,2,5000)


@pytest.mark.parametrize('fault',['shift','missing','failure','clock','summary','duplicate'])
def test_invalid_receipts_fail_closed(fault):
    rows,clocks=receipts()
    if fault=='shift':rows[2]['scan_origin_ns']+=1
    elif fault=='missing':rows.pop(3)
    elif fault=='failure':rows[3]['exit_code']=3
    elif fault=='clock':clocks[0]['origin_ns']+=1
    elif fault=='summary':rows[-1]['pending_high_water']=0
    else:rows.insert(2,copy.deepcopy(rows[1]))
    with pytest.raises(ValueError):evaluate(rows,clocks,100,2)
