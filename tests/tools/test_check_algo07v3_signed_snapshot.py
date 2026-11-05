import subprocess
import sys


def test_signed_comparison_helper_runs_with_the_legacy_import_guard_enabled():
    code = '''
import sys
from check_algo07v3_track_preparation import deny_legacy
sys.addaudithook(deny_legacy)
from check_algo07v3_position import signed_snapshot
from types import SimpleNamespace
p=SimpleNamespace(calculate=lambda x:{'score':1.},state=lambda x:{},
    residual=lambda x:[],conditional_frequency=lambda x:([],[]),
    members=[],labels=[],keep=[],reference=[],events=[],event_start=0)
context=dict(scan=object(),base=p,x=[0.,0.],original_protected={2,1})
result=signed_snapshot(context)
assert result['original_protected']==[1,2]
assert result['base']['calculated']=={'score':1.}
assert not any(n.startswith('algo0') for n in sys.modules)
'''
    subprocess.run([sys.executable, '-B', '-c', code], check=True, timeout=30)
