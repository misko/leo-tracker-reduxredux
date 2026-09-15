"""Real saved-IQ checks of the live probe's actual ranking function."""
import ctypes as c,json,hashlib,os
from pathlib import Path
import numpy as np
from tests.starlink_glrt import test_cpu_live_probe as fixture
BASE=Path(__file__).parent
out=BASE/'live-scan64-ranking-v1';out.mkdir(exist_ok=False)
class Factory:
    def mktemp(self,name):
        p=out/name;p.mkdir();return p
lib,refs=fixture.live_api.__wrapped__(Factory())
bank=fixture.bank();ports=fixture.Ports();checks=[]
manifest=json.loads((BASE/'short-fft-scan-host-v1-results/result.json').read_text())
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for case in manifest['cases']:
    if case['fft']!=4096:continue
    label=f"{case['label']}-{case['number']}";directory=out/label;directory.mkdir()
    path=BASE/'combined-pilot-controls-v1'/label/'iq.ci16';assert digest(path)==case['input_sha256']
    raw=np.fromfile(path,dtype='<i2').reshape(-1,2);iq=np.ascontiguousarray(raw[:14000])
    journal=BASE/'short-fft-scan-host-v1-results'/f'{label}-fft4096.jsonl'
    assert digest(journal)==case['journal_sha256']
    rows=[json.loads(line) for line in journal.read_text().splitlines()]
    epochs=np.array([r['epoch'] for r in rows[:-1]],dtype=np.uint32)
    scores=np.full(64,999.,dtype=np.float64);selected=c.c_uint(999)
    handle=lib.live_new(refs.ctypes.data,bank.ctypes.data,os.fsencode(directory),c.byref(ports),60000000)
    try:
        assert lib.live_set_dwell(handle,b'1536-selected-observer3-scan64',(c.c_uint64*4)())==0
        assert lib.live_rank(handle,iq.ctypes.data,epochs.ctypes.data,64,scores.ctypes.data,c.byref(selected))==0
        np.testing.assert_allclose(scores,[r['rank_power'] for r in rows[:-1]],rtol=2e-12,atol=2e-15)
        assert selected.value+1==case['winner']
        checks.append(dict(label=label,winner=selected.value+1,scores=scores.tolist()))
    finally:lib.live_free_unstarted(handle)
result=dict(status='pass',cases=checks,scores_checked=1664,new_rf_samples=0,
    source_sha256=digest(fixture.ROOT/'tools/glrt_cpu_live_probe.c') if hasattr(fixture,'ROOT') else digest(Path('/home/mouse9911/gits/plutosdr-fw-radio20-tracking/tools/glrt_cpu_live_probe.c')),
    reviewer_sha256=digest(Path(__file__)))
with (out/'result.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print('1664 actual live-ranking scores match independently checked saved-IQ spectra')
