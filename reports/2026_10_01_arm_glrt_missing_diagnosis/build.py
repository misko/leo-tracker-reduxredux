"""Rebuild frozen ARM implementation with only its coarse rejection disabled."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
RECEIPT=Path('/var/tmp/leo-native-glrt-headroom-final-v3-frozen/build-receipt.json')
SOURCE=Path('/var/tmp/leo-glrt-missing-diagnosis-source')

def main():
    receipt=json.loads(RECEIPT.read_text())
    original=Path(receipt['source_root'])
    for p,h in receipt['sources'].items():
        assert hashlib.sha256((original/p).read_bytes()).hexdigest()==h,p
    out=HERE/'ungated-build';out.mkdir(exist_ok=False)
    (out/'objects').mkdir()
    replacements={str(original):str(SOURCE),
        '/var/tmp/leo-native-glrt-headroom-final-work-v3-frozen':str(out),
        '/var/tmp/leo-native-glrt-headroom-final-v3-frozen':str(out)}
    commands=[]
    for command in receipt['commands']:
        argv=command['argv'][:]
        for i,a in enumerate(argv):
            for old,new in replacements.items():a=a.replace(old,new)
            argv[i]=a
        if '-c' in argv:argv.insert(1,'-DLEO_DIAG_BYPASS_COARSE=1')
        result=subprocess.run(argv,text=True,capture_output=True,env={**os.environ,'TMPDIR':'/var/tmp'})
        commands.append({'argv':argv,'returncode':result.returncode,'stderr':result.stderr})
        if result.returncode:
            print(result.stderr);raise RuntimeError('Build failed')
    (HERE/'build.json').write_text(json.dumps({'parent_receipt_sha256':hashlib.sha256(RECEIPT.read_bytes()).hexdigest(),
        'commands':commands,'modified_full_search_sha256':hashlib.sha256((SOURCE/'kernel/private/full_search.c').read_bytes()).hexdigest()},indent=2)+'\n')

if __name__=='__main__':main()
