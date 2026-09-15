"""No-radio operator admission checks with an explicit refused lease."""
import importlib.util,json,sys,types
from pathlib import Path
import pytest

BASE=Path(__file__).parent
SERIAL='1040005e0b100007100010000bf33a5d4d'


@pytest.mark.parametrize('rate',[30000000,60000000])
@pytest.mark.parametrize('channels',[(3,4,3),(1,2,3,4),(3,4,3,4)])
def test_valid_plan_is_bound_and_refused_before_radio_contact(monkeypatch,tmp_path,rate,channels):
    class Refused(Exception):pass
    calls=[]
    class Authority:
        def __init__(self,*args):calls.append(args)
        def claim(self,*args,**kwargs):raise Refused('test lease refusal')
    live=types.ModuleType('qualify_glrt_cpu_live20')
    live.EVIDENCE=BASE;live.ENDPOINT=(SERIAL,'192.168.1.20')
    live.g=types.SimpleNamespace(deployment_identity=lambda *a,**k:({'expected_firmware':f'glrt-iq-tracking-r{rate}-v1'},None))
    live.LocalCaptureAuthority=Authority;live.RadioResource=lambda *a:a
    live.CaptureTaskKind=types.SimpleNamespace(QUALIFICATION='qualification')
    monkeypatch.setitem(sys.modules,'qualify_glrt_cpu_live20',live)
    spec=importlib.util.spec_from_file_location('operator_test',BASE/'qualify_frequency_revisits.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    out=tmp_path/'out'
    monkeypatch.setattr(sys,'argv',['operator',str(out),'receipt',*map(str,channels)])
    with pytest.raises(Refused):module.main()
    r=json.loads((out/'operator.json').read_text())
    assert r['status']=='admission_refused' and r['rf_samples_collected']==0
    assert r['visit_count']==len(channels) and r['serial']==SERIAL and r['rate']==rate
    assert r['lo_plan_hz']==[1190312500+(n-1)*250000000 for n in channels]
    assert r['rf_sample_limit']==len(channels)*25165824 and r['retention_mode']=='selected_windows'
    assert len(calls)==1


@pytest.mark.parametrize('channels',[(3,3,4),(1,2,5),(0,2,1),(1,2,3,3)])
def test_bad_plan_is_rejected_before_identity_or_evidence(monkeypatch,tmp_path,channels):
    live=types.ModuleType('qualify_glrt_cpu_live20');live.EVIDENCE=BASE
    monkeypatch.setitem(sys.modules,'qualify_glrt_cpu_live20',live)
    spec=importlib.util.spec_from_file_location('operator_test',BASE/'qualify_frequency_revisits.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(sys,'argv',['operator',str(tmp_path/'out'),'receipt',*map(str,channels)])
    with pytest.raises(ValueError):module.main()
    assert not list(tmp_path.iterdir())
