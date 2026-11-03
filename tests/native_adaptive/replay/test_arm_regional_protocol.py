import copy
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('regional',
    Path(__file__).resolve().parents[3]/'tools/run_arm_regional_qualification.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def protocol():
    return {**{key:{'device_path':'/mnt/glrtbench/diagnostic/'+key,'sha256':'a'*64}
              for key in ('search_binary','score_binary','input')},
            'timeout_s':600,'workers':2,'prior':[38.58,-121.49,250]}


def test_bounded_explicit_protocol():
    module.validate(protocol())
    for key,value in [('timeout_s',601),('workers',3),('prior',[float('nan'),0,250]),
                      ('prior',[91,0,250]),('prior',[0,0,-1])]:
        p=protocol();p[key]=value
        with pytest.raises(ValueError):module.validate(p)


def test_paths_and_hashes_are_required():
    for key,value in [('device_path','/mnt/glrtbench/../other'),
                      ('device_path','relative'),('device_path','/etc/file'),('sha256','x'*64)]:
        p=copy.deepcopy(protocol());p['input'][key]=value
        with pytest.raises(ValueError):module.validate(p)


def test_measurement_guard_covers_regional_and_paced_work():
    assert module.measurement_active('42 root /mnt/glrtbench/native-adaptive/current/measure-run 600 /mnt/glrtbench/scorer search x')
    assert module.measurement_active('42 root /mnt/glrtbench/modular-ds9-iq-v1/leo-recorded-graph-arm x')
    assert not module.measurement_active('42 root sshd\n43 root ps')
