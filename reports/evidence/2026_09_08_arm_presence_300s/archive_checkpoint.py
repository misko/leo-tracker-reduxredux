"""Retain lossless execution evidence and render measured ARM latency."""
from pathlib import Path
import gzip
import json
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from tools.native_presence import ROOT
from tools.qualify_native_presence import digest, write_json

source=Path('/tmp/leo-presence-arm-profile.UuBXXp')
destination=ROOT/'reports/evidence/2026_09_08_arm_presence_300s'
figures=ROOT/'reports/figures/2026_09_08_arm_presence_300s'
assert json.loads((source/'replay-300s-resumed/end.json').read_text())['remote_scratch_retained'] is None
destination.mkdir(exist_ok=False)
figures.mkdir(exist_ok=False)
entries=[]
selected=[]
for directory in ('baseline','baseline-v2','variants','qualification','sanitizer','replay-300s','replay-300s-resumed'):
    selected.extend(p for p in (source/directory).rglob('*') if p.is_file() and p.suffix in ('.json','.jsonl'))
selected.extend(source/p for p in ('optimization-tests.xml','regression-final.xml','port-regression.xml',
    'profile_saved.py','profile_saved_rejected_builder.py','profile_variants.py','qualify_optimization.py',
    'sanitize_optimization.py','replay_300s.py','resume_replay_300s.py','archive_checkpoint.py',
    'audit_replay_inputs.py','arrival-audit.json'))
for path in sorted(set(selected)):
    relative=path.relative_to(source)
    raw=path.read_bytes()
    compressed=path.suffix in ('.jsonl','.xml') or len(raw)>65536
    target=destination/str(relative)
    if compressed:
        target=target.with_name(target.name+'.gz')
    target.parent.mkdir(parents=True,exist_ok=True)
    encoded=gzip.compress(raw,compresslevel=9,mtime=0) if compressed else raw
    with target.open('xb') as stream:
        stream.write(encoded)
    assert (gzip.decompress(encoded) if compressed else encoded)==raw
    entries.append(dict(path=str(target.relative_to(destination)),source=str(path),
                        original_sha256=digest(path),sha256=digest(target),original_bytes=len(raw),bytes=len(encoded)))

runs=[]
for directory,label in [('replay-300s','0-5000000-baseline'),('replay-300s','1-5000000-combined'),
                        ('replay-300s-resumed','2-2500000-combined'),('replay-300s-resumed','3-2500000-baseline')]:
    path=source/directory/f'{label}.verification.json'
    checked=json.loads(path.read_text())
    assert checked['verified'] and checked['raw_sha256']==digest(source/directory/f'{label}.jsonl')
    runs.append(dict(label=label,**checked))
assert sum(run['executions'] for run in runs)==5500
write_json(destination/'combined-summary.json',dict(runs=runs,live_rf=False,goal_complete=False,
    full_duration_jobs=5000,short_baseline_jobs=500))

fig,axes=plt.subplots(2,1,figsize=(11,6.4),sharex=True,sharey=True,layout='constrained')
for ax,rate,directory,label,color in zip(axes,(5000000,2500000),('replay-300s','replay-300s-resumed'),
                                       ('1-5000000-combined','2-2500000-combined'),('#c35e16','#1d719d'),strict=True):
    rows=[json.loads(line) for line in (source/directory/f'{label}.jsonl').read_text().splitlines()][:-1]
    timing=np.array([row['delivery_latency_ms'] for row in rows])
    x=np.arange(len(rows))*.12
    ax.scatter(x,timing,s=3,alpha=.27,color=color,rasterized=True)
    bins=[timing[i:i+250] for i in range(0,len(timing),250)]
    ax.plot(np.arange(15,300,30),[np.quantile(v,.99) for v in bins],color=color,lw=2,label='p99 per 30 s')
    ax.axhline(120,color='#9a2323',ls='--',lw=1,label='120 ms arrival period')
    ax.axhline(100,color='#555555',ls=':',lw=1,label='100 ms engineering target')
    ax.set_title(f'{rate/1e6:g} MS/s — 2,500/2,500 results; p99 {np.quantile(timing,.99):.2f} ms; max {timing.max():.2f} ms',loc='left',fontsize=11)
    ax.set_ylabel('Copy-to-result latency (ms)')
    ax.grid(alpha=.15)
axes[0].legend(loc='lower right',fontsize=8,ncol=3)
axes[-1].set_xlabel('Replay time (s); 16 saved RX1 dwells repeated per rate')
axes[-1].set_xlim(0,300)
axes[-1].set_ylim(25,132)
fig.suptitle('Optimized GLRT worker: real ARM execution over 300 seconds\nSaved-IQ replay only — no live acquisition, DMA/retune load, or duty proof',fontsize=12)
figure=figures/'worker-latency-300s.png'
fig.savefig(figure,dpi=170)
plt.close(fig)

tests=[]
for filename in ('regression-final.xml','port-regression.xml'):
    suites=ET.parse(source/filename).getroot().findall('testsuite')
    counts={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    assert not counts['failures'] and not counts['errors'] and not counts['skipped']
    tests.append(dict(source=filename,**counts))
receipt=dict(schema='org.leo.research.arm-presence-300s-checkpoint/v1',implementation_commit='4544f0dc',
             source_directory=str(source),evidence=entries,tests=tests,
             figure=dict(path=str(figure.relative_to(ROOT)),sha256=digest(figure)),
             summary_sha256=digest(destination/'combined-summary.json'),
             live_rf=False,deployed=False,firmware_changed=False,goal_complete=False,
             limitations=['saved-IQ burst-per-dwell pacing, not archived block/event arrival timing',
                          'no actual acquisition IRQ/network contention',
                          'numerical parity is not new detector qualification',
                          'experimental optimizations and runtime classification remain off by default'])
write_json(destination/'receipt.json',receipt)
print(json.dumps(dict(artifacts=len(entries),bytes=sum(e['bytes'] for e in entries),tests=tests,figure=str(figure)),indent=2))
