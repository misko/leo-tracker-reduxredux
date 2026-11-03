import os
from pathlib import Path
import subprocess

import pytest

from leo.native_pipeline.projection import integer_support


@pytest.fixture(scope='module')
def binary(tmp_path_factory):
    root=Path(__file__).resolve().parents[3];out=tmp_path_factory.mktemp('integer-support')/'port'
    subprocess.run(['g++','-std=c++17','-O2','-fno-fast-math','-ffp-contract=off','-pthread',
        str(root/'native/adaptive/runtime/runtime.cpp'),
        str(root/'native/adaptive/runtime/integer_support_cli.cpp'),'-o',str(out)],
        check=True,capture_output=True,timeout=60,env={**os.environ,'TMPDIR':'/var/tmp'})
    return out


@pytest.mark.parametrize('rate',[750000,2500000,10000000])
def test_support_geometry_and_moments_against_python(binary,rate):
    samples=rate//50
    epochs=[0,1,rate//1500,rate//750-1,samples*9//10,samples-1000]
    if rate==2500000:epochs=sorted(set(epochs+[722,1666,3332,45000,49000]))
    result=subprocess.run([str(binary)],input=''.join(f'{rate} {samples} {e}\n' for e in epochs),
        text=True,capture_output=True,check=True,timeout=5)
    for epoch,row in zip(epochs,result.stdout.splitlines(),strict=True):
        actual=list(map(float,row.split()));expected=integer_support(epoch,rate,samples)
        assert actual[:3]==[expected.start,expected.end,expected.center]
        assert abs(actual[3]-expected.moments[2])<=1e-18
        assert abs(actual[4]-expected.moments[3])<=1e-20


@pytest.mark.parametrize('line',['2500000 50000 -1','2500000 50000 50000','2500000 50000 1 extra'])
def test_invalid_support_input_fails(binary,line):
    result=subprocess.run([str(binary)],input=line+'\n',text=True,capture_output=True,timeout=5)
    assert result.returncode==2
    assert not result.stdout
