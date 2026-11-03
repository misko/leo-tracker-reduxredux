import importlib.util
from pathlib import Path


def test_staging_comparison_excludes_only_row_timing():
    path=Path(__file__).resolve().parents[3]/'tools/qualify_native_iq_staging.py'
    spec=importlib.util.spec_from_file_location('iq_staging',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    a={'rows':[{'timings_ms':{'total_cpu':5},'candidate_count':1,'candidates':[{'cfo_hz':42}]}]}
    b={'rows':[{'timings_ms':{'total_cpu':6},'candidate_count':1,'candidates':[{'cfo_hz':42}]}]}
    assert module.scientific_rows(a)==module.scientific_rows(b)
    b['rows'][0]['candidates'][0]['cfo_hz']=43
    assert module.scientific_rows(a)!=module.scientific_rows(b)
    assert 'timings_ms' in a['rows'][0]
