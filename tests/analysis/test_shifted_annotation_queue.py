from pathlib import Path
import pytest
from freeze_shifted_annotation_inventory import select_rows
from run_annotation_inventory import annotation_command,pending_jobs


def test_only_wholly_unowned_still_insufficient_curves_enter_shifted_queue():
    source=[dict(track_id=str(i),job_id='scan',component=f'CH{i}',points=20+i,state='queued') for i in range(5)]
    ledger=[dict(track_id=str(i),state='insufficient_partitions',annotation_source='old') for i in range(5)]
    geometry=[dict(track_id=str(i),job_id='scan',component=f'CH{i}',new_geometry_support='True',whole_curve_unowned='True') for i in range(5)]
    ledger[0]['predictive_recheck_state']='conditionally_supported_identity'
    geometry[1]['whole_curve_unowned']='False'
    geometry[2]['new_geometry_support']='False'
    assert [r['track_id'] for r in select_rows(geometry,ledger,source)]==['4','3']
    geometry[3]['component']='wrong'
    with pytest.raises(ValueError,match='identity'):select_rows(geometry,ledger,source)


def test_shifted_origin_cannot_silently_change_calibration_role():
    row=dict(track_id='target',inventory='/inventory.json')
    with pytest.raises(ValueError,match='distinct predictive'):
        annotation_command(row,Path('/out'),shifted_block_origin=True,distinct_partitions=True)
    cmd=annotation_command(row,Path('/out'),predictive_member=True,distinct_partitions=True,shifted_block_origin=True)
    assert '--shifted-block-origin' in cmd and '--uncalibrated-phase-mixture' in cmd


def test_reconciled_remaining_scope_prevents_duplicate_cross_queue_work(tmp_path):
    rows=[dict(track_id=str(i),state='queued') for i in range(4)]
    assert [r['track_id'] for r in pending_jobs({'rows':rows},tmp_path,1,remaining_ids={'1','3'})]==['1']
    assert pending_jobs({'rows':rows},tmp_path,4,remaining_ids=set())==[]
