import importlib.util
import json
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('ds7_glrt_run',Path(__file__).with_name('run.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def fixture(tmp_path):
    plan={'dataset_sha256':'ds7','maximum_uncompressed_iq_bytes':100,
          'captures':[{'session_id':'a','sample_rate_hz':2500000,'manifest_sha256':'source','visit_indices':[1,2]}]}
    path=tmp_path/'plan.json';path.write_text(json.dumps(plan))
    receipt={'complete':True,'plan_sha256':module.sha(path),'dataset_sha256':'ds7','iq_bytes':80,
        'rows':[{'session_id':'a','rate_hz':2500000,'manifest_sha256':'source','visit_index':v} for v in (1,2)]}
    return plan,receipt,path


def test_validates_complete_ordered_cohort(tmp_path):
    plan,receipt,path=fixture(tmp_path);module.validate_inputs(plan,receipt,path)
    receipt['rows'].reverse()
    with pytest.raises(ValueError,match='membership/order'):module.validate_inputs(plan,receipt,path)


@pytest.mark.parametrize('mutation',['plan','source','missing','incomplete','budget'])
def test_rejects_unbound_or_incomplete_data(tmp_path,mutation):
    plan,receipt,path=fixture(tmp_path)
    if mutation=='plan':path.write_text('{}')
    elif mutation=='source':receipt['rows'][0]['manifest_sha256']='changed'
    elif mutation=='missing':receipt['rows'].pop()
    elif mutation=='incomplete':receipt['complete']=False
    elif mutation=='budget':receipt['iq_bytes']=101
    with pytest.raises(ValueError):module.validate_inputs(plan,receipt,path)
