"""Archive completed modeled SDK measurements; no executable or IQ publication."""
from pathlib import Path
import gzip
import json
import xml.etree.ElementTree as ET
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from tools.native_presence import ROOT
from tools.qualify_native_presence import digest,write_json

source=Path('/tmp/leo-glrt-sdk-blocks.XtW3os')
destination=ROOT/'reports/evidence/2026_09_08_scanner_glrt_sdk_replay'
figures=ROOT/'reports/figures/2026_09_08_scanner_glrt_sdk_replay'
assert json.loads((source/'arm-runs/end.json').read_text())['remote_scratch_retained'] is None
summary=json.loads((source/'arm-runs/summary.json').read_text())
assert len(summary['runs'])==8 and all(r['verified'] for r in summary['runs'])
destination.mkdir(exist_ok=False)
figures.mkdir(exist_ok=False)
files=list(p for p in source.rglob('*') if p.is_file() and p.suffix in ('.json','.jsonl','.xml','.py'))
entries=[]
for p in sorted(files):
    raw=p.read_bytes()
    relative=p.relative_to(source)
    target=destination/relative
    compressed=p.suffix in ('.jsonl','.xml') or len(raw)>65536
    if compressed:
        target=target.with_name(target.name+'.gz')
    target.parent.mkdir(parents=True,exist_ok=True)
    encoded=gzip.compress(raw,compresslevel=9,mtime=0) if compressed else raw
    with target.open('xb') as stream:
        stream.write(encoded)
    assert (gzip.decompress(encoded) if compressed else encoded)==raw
    entries.append(dict(path=str(target.relative_to(destination)),sha256=digest(target),source=str(p),
                        original_sha256=digest(p),bytes=len(encoded),original_bytes=len(raw)))

fig,axes=plt.subplots(2,2,figsize=(12,7),layout='constrained')
for row,(rate,label,color) in enumerate(((5000000,'6-5000000-enabled1-delay2-jitter40','#bc5d1e'),
                                      (2500000,'7-2500000-enabled1-delay2-jitter40','#1b719d'))):
    run=next(r for r in summary['runs'] if r['label']==label)
    rows=[json.loads(line) for line in (source/'arm-runs'/f'{label}.jsonl').read_text().splitlines()]
    blocks=[r for r in rows if r['kind']=='block']
    x=np.array([r['arrival_ms']/1000 for r in blocks])
    timing=np.array([r['callback_wall_ms'] for r in blocks])
    ax=axes[row,0]
    ax.scatter(x,timing,s=2,alpha=.25,color=color,rasterized=True)
    ax.axhline(run['nominal_block_period_ms'],color='#982f2f',ls='--',lw=1,label='Nominal block period')
    ax.set_title(f'{rate/1e6:g} MS/s SDK callback: p99 {run["callback_wall_ms"]["p99"]:.2f} ms',fontsize=11,loc='left')
    ax.set_ylabel('Callback wall time (ms)')
    ax.set_xlabel('Modeled replay time (s)')
    ax.set_xlim(0,300)
    ax.grid(alpha=.15)
    ax.legend(fontsize=8)
    ax=axes[row,1]
    fields=['callback_wall_ms','worker_wall_ms','ready_callback_to_frame_ms']
    locations=np.arange(3)
    ax.bar(locations,[run[k]['p99'] for k in fields],color=[color,color,'#65737d'],alpha=.8)
    ax.scatter(locations,[run[k]['max'] for k in fields],color='#333333',marker='_',s=100,label='Maximum')
    for location,key in zip(locations,fields,strict=True):
        ax.text(location,run[key]['p99']+3,f'{run[key]["p99"]:.1f}',ha='center',fontsize=9)
    ax.set_xticks(locations,['SDK\ncallback','Worker\ncompute','Ready-to-frame\ndelivery'])
    ax.set_ylabel('p99 wall time (ms)')
    ax.set_title(f'{run["results"]}/{run["jobs"]} source-bound results; no busy/lost results',loc='left',fontsize=11)
    ax.set_ylim(0,max(run[k]['max'] for k in fields)*1.2)
    ax.grid(axis='y',alpha=.15)
    ax.legend(fontsize=8)
fig.suptitle('Actual ARM acquisition SDK: 300-second modeled block replay\nTwo-block event delay + 40 ms delay every fourth block; saved RX1, synthetic RX0/transition padding; no RF',fontsize=12)
figure=figures/'sdk-callback-and-delivery.png'
fig.savefig(figure,dpi=170)
plt.close(fig)
suite=ET.parse(source/'regression.xml').getroot().find('testsuite')
assert int(suite.attrib['tests'])==185 and all(int(suite.attrib[k])==0 for k in ('errors','failures','skipped'))
write_json(destination/'receipt.json',dict(schema='org.leo.research.scanner-glrt-sdk-replay-checkpoint/v1',
    evidence=entries,tests=dict(suite.attrib),figure=dict(path=str(figure.relative_to(ROOT)),sha256=digest(figure)),
    source=str(source),live_rf=False,deployed=False,firmware_changed=False,goal_complete=False,
    limitations='Modeled producer/SDK/worker/frame-codec workload; not actual RF, IIO refill, iiOD network or live duty'))
print(json.dumps(dict(files=len(entries),bytes=sum(e['bytes'] for e in entries),figure=str(figure)),indent=2))
