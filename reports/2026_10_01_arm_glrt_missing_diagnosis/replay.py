"""Bounded physical saved-IQ ablation; no RF or production changes."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time
import numpy as np
from leo.storage.adaptive_hop import AdaptiveHopIqStore

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/'2026_09_30_arm_streaming_tracks'))
from run_device import SSH,AUTH,OPTIONS

REMOTE='/mnt/glrtbench/missing-long-gate-ablation-20261001'
PRIOR='/mnt/glrtbench/ds9-native-comparison-20260930'
SESSION='scan-fw-f363c7f29141d0b1'

def run(argv,timeout=90):
    return subprocess.run(argv,capture_output=True,text=True,check=True,timeout=timeout)

def main():
    started=time.monotonic()
    records=json.loads((HERE/'missing.json').read_text())
    visits=sorted({r['visit'] for r in records})
    inventory={r['visit']:r for r in json.loads((HERE.parent/'2026_09_30_arm_full_scan_comparison/arm-v2/inventory.json').read_text())}
    out=HERE/'physical';out.mkdir(exist_ok=False)
    run(SSH+['mkdir '+REMOTE])
    binary=HERE/'ungated-build/leo-native-glrt-bench'
    run(AUTH+['scp','-O']+OPTIONS+[str(binary),f'root@192.168.1.15:{REMOTE}/bench-ungated'])
    uploaded=run(SSH+[f'chmod 755 {REMOTE}/bench-ungated; sha256sum {REMOTE}/bench-ungated {PRIOR}/bench-ordinary']).stdout
    assert uploaded.splitlines()[0].split()[0]==hashlib.sha256(binary.read_bytes()).hexdigest()
    assert uploaded.splitlines()[1].split()[0]=='9b0c777653a97766ef060e4945c840308e3d6b48365b1412f6219a335d572d3e'
    (out/'binary-hashes.txt').write_text(uploaded)
    store=AdaptiveHopIqStore('/srv/bulk/leo',read_only=True)
    checked=[]
    try:
        session=store.inspect(SESSION)
        with store.reader(SESSION,expected=session) as reader,tempfile.TemporaryDirectory(prefix='leo-gate-ablation-',dir='/var/tmp') as tmp:
            for begin in range(0,len(visits),8):
                assert time.monotonic()-started<600
                group=visits[begin:begin+8];lines=[];hashes=[]
                bundle=Path(tmp)/'inputs.tar'
                with tarfile.open(bundle,'w') as archive:
                    for local,visit in enumerate(group):
                        doc,values=reader.read_visit_ci16(visit)
                        raw=np.asarray(values,dtype='<i2',order='C').tobytes()
                        sha=hashlib.sha256(raw).hexdigest()
                        assert sha==inventory[visit]['raw_sha256']
                        assert doc.event.model_dump(mode='json')==inventory[visit]['event']
                        name=f'visit-{visit:06d}.ci16';info=tarfile.TarInfo(name);info.size=len(raw);archive.addfile(info,io.BytesIO(raw))
                        hashes.append(f'{sha}  {name}\n');checked.append({'visit':visit,'raw_sha256':sha})
                        edge=inventory[visit]['event']['target']['edge']
                        lines.append(f'{local}\t2500000\t120\t120\t{PRIOR}/{edge}-exact.c128\t{PRIOR}/{edge}-control.c128\t{REMOTE}/{name}')
                    for name,data in {'batch.tsv':'\n'.join(lines)+'\n','batch.sha256':''.join(hashes)}.items():
                        raw=data.encode();info=tarfile.TarInfo(name);info.size=len(raw);archive.addfile(info,io.BytesIO(raw))
                run(AUTH+['scp','-O']+OPTIONS+[str(bundle),f'root@192.168.1.15:{REMOTE}/inputs.tar'])
                check=run(SSH+[f'cd {REMOTE} && tar -xf inputs.tar && sha256sum -c batch.sha256']).stdout
                assert check.count(': OK')==len(group)
                for label,binary_path in [('ordinary',PRIOR+'/bench-ordinary'),('ungated',REMOTE+'/bench-ungated')]:
                    r=run(SSH+[f'ulimit -v 220000; {binary_path} --manifest {REMOTE}/batch.tsv'])
                    (out/f'{label}-{begin:03d}.jsonl').write_text(r.stdout)
                    (out/f'{label}-{begin:03d}.stderr').write_text(r.stderr)
                (out/f'visits-{begin:03d}.json').write_text(json.dumps(group)+'\n')
                # Remove only temporary IQ staging created by this replay.
                run(SSH+['rm '+ ' '.join(f'{REMOTE}/visit-{v:06d}.ci16' for v in group)+f' {REMOTE}/inputs.tar'])
                print(f'Replayed {begin+len(group)}/{len(visits)} saved dwells, both builds',flush=True)
    finally:store.close()
    (out/'receipt.json').write_text(json.dumps({'visits':checked,'elapsed_s':time.monotonic()-started,
        'scope':'Physical PLUTO+ saved-IQ gate ablation; no RF'},indent=2)+'\n')

if __name__=='__main__':main()
