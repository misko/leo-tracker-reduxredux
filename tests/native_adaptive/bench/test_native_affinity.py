import os
from pathlib import Path
import subprocess
import sys


def test_affinity_launcher(tmp_path):
    source=Path(__file__).resolve().parents[3]/'tools/native_affinity.c'
    binary=tmp_path/'affinity'
    subprocess.run(['cc','-Wall','-Wextra','-Werror',str(source),'-o',str(binary)],check=True)
    for args in [[],['0','true'],['4','true'],['11','true'],['x','true']]:
        assert subprocess.run([str(binary),*args],capture_output=True).returncode==2
    allowed=os.sched_getaffinity(0)
    for cpu in (0,1):
        result=subprocess.run([str(binary),str(1<<cpu),sys.executable,'-c',
            'import os,sys; print(sorted(os.sched_getaffinity(0))); print(sys.argv[1]); sys.exit(17)',
            'argument with spaces'],capture_output=True,text=True)
        if cpu in allowed:
            assert result.returncode==17
            assert result.stdout==f'[{cpu}]\nargument with spaces\n'
        else:
            assert result.returncode==3 and not result.stdout
