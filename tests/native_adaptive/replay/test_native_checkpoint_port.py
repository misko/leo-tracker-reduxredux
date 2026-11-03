import csv
import io
import os
from pathlib import Path
import subprocess

import pytest

from leo.native_pipeline.projection import WindowAuthority,project_integer_candidates


@pytest.fixture(scope='module')
def binary(tmp_path_factory):
    root=Path(__file__).resolve().parents[3];out=tmp_path_factory.mktemp('native-checkpoint')/'project'
    src=root/'native/adaptive/runtime'
    subprocess.run(['g++','-std=c++17','-O2','-fno-fast-math','-ffp-contract=off','-pthread',
                   *(str(src/p) for p in ['observations_cli.cpp','runtime.cpp','projection.cpp']),'-o',str(out)],
                   check=True,capture_output=True,timeout=60,env={**os.environ,'TMPDIR':'/var/tmp'})
    return out


def test_checkpoint_matches_python_and_filters_nonpassing(binary):
    capture='sha256:'+'a'*64;analysis='sha256:'+'b'*64
    authority=WindowAuthority(capture,analysis,0,0,0,1,'lower',11200000000.,2500000,50000,100,100,1000000000)
    values=[2500000,100,1000000000,1,0,100,0,0,1,0,11200000000,0,capture,analysis,1,0,722,0,-100,.4,.1,.3,1]
    line='\t'.join(map(str,values))+'\n'
    rejected=values.copy();rejected[15]=1;rejected[19]=.11;rejected[21]=.01
    result=subprocess.run([str(binary),'--checkpoint'],input=line+'\t'.join(map(str,rejected))+'\n',
                          capture_output=True,text=True,check=True,timeout=5)
    rows=list(csv.DictReader(io.StringIO(result.stdout),delimiter='\t'));assert len(rows)==1
    expected=project_integer_candidates(authority,[dict(epoch=722,tracking_cfo_hz=-100,
        exact_score=.4,control_score=.1,margin=.3,glrt_complete=1)])[0].observation
    assert rows[0]['candidate_id']==expected[0]
    assert int(rows[0]['support_center_utc_ns'])==expected[7]
    assert float(rows[0]['margin'])==expected[12]
    legacy=subprocess.run([str(binary)],input=line,capture_output=True,text=True,check=True,timeout=5)
    assert legacy.stdout.startswith(expected[0]+'\t')


def test_unknown_cli_mode_is_rejected(binary):
    result=subprocess.run([str(binary),'--unknown'],capture_output=True,text=True,timeout=5)
    assert result.returncode==2 and not result.stdout
