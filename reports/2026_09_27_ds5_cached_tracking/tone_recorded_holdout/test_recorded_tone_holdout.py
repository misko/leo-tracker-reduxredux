from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_holdout as study


def test_original_holdout_membership_and_unknown_truth_without_iq():
    rows=study.membership()
    assert len(rows)==128
    assert {r['session_id'] for r in rows}.isdisjoint({
        'scan-fw-40ebc07665464c7d','scan-fw-e76c229e9dc498b3'})
    for row in rows:
        c=study.case(row)
        assert c.split=='holdout' and c.activity_policy=='recorded_unknown'
        assert all(not r.constructed_negative and not r.pilots for r in c.receivers)
        assert c.source_counter==row['source_start_counter']


def test_timed_call_and_summary_without_optional_raw_comparator():
    value,timing=study.engine.raw_runner.timed(lambda:19)
    assert value==19 and timing['process_cpu_ms']>=0
    summary=study.engine.summarize('real',[])
    assert summary['rescue']['raw_rescue']['visits']==0
