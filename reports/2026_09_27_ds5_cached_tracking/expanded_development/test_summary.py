from pathlib import Path
import importlib.util
import sys
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('expanded_receipt_summary',HERE/'summarize.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)


def test_visit_success_does_not_hide_receiver_identity_loss():
    assessments=[dict(reference_active=True,matched_reference=True,lost_reference=False,
                      additional_or_mismatched=False,candidate_active=True),
                 dict(reference_active=True,matched_reference=False,lost_reference=True,
                      additional_or_mismatched=True,candidate_active=True)]
    row=dict(case_id='fixture',rate_hz=2500000,assessments=assessments,
             decisions=[{'route':'guided'},{'route':'guided'}],application_pair_inventory=[],
             timings={'application':{'process_cpu_ms':1000},'candidate':{'process_cpu_ms':10,'wall_ms':11}})
    result=module.summarize([row])['2500000']
    assert result['lost_reference_visits']==0 and result['lost_reference']==1
    assert result['additional_or_mismatched']==1 and result['matched_reference']==1
    assert result['cpu_speedup']==100
