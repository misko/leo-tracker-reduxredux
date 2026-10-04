"""All refined candidates versus endpoints of within-probe <300 Hz pairs."""
import json,collections,itertools,hashlib
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

B=Path('/srv/bulk/leo/ds13-spline-replay.4hywxT/full-scan-A-refinement')
source=B/'refined.json';receipt=json.loads(source.read_text());records=receipt['records']
frozen=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_03_ds13_coverage_goal/frozen/A-observations.npz')
with np.load(frozen) as z:a={k:z[k].copy() for k in z.files}
rows=np.array([r['row_index'] for r in records]);freq=np.array([r['output_hz'] for r in records]);assert len(set(rows))==7382
period=1/4.4e-6;wrap=lambda x:(x+period/2)%period-period/2
groups=collections.defaultdict(list)
for i,r in enumerate(records):groups[tuple(r['probe_key'])].append(i)
keep=np.zeros(len(rows),bool);pairs=0;probes=0
for group in groups.values():
    found=False
    for i,j in itertools.combinations(group,2):
        if abs(wrap(freq[i]-freq[j]))<300:
            keep[i]=keep[j]=True;pairs+=1;found=True
    probes+=found
assert pairs==2709
owners={x['row_index'] for x in json.loads((B/'solver/A-fitted-c.json').read_text())['final']['assignments']}
assigned=np.array([int(r) in owners for r in rows]);out=B/'within-probe-300hz';out.mkdir(exist_ok=True)
summary=dict(total_candidates=len(rows),qualifying_pairs=pairs,qualifying_unique_candidates=int(sum(keep)),qualifying_probes=probes,qualifying_assigned=int(sum(keep&assigned)),qualifying_unassigned=int(sum(keep&~assigned)),threshold_hz=300,rule='Keep both endpoints of any same-probe pair with circular separation strictly below 300 Hz. Plot each candidate once; no merging, orbit gate, or reassignment.',sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,frozen)},rows=rows[keep].tolist())
for name,mask,title in [('all',np.ones(len(rows),bool),'All refined candidates'),('below-300hz',keep,'Candidates with a same-window neighbor <300 Hz away')]:
    fig,axes=plt.subplots(4,2,figsize=(14,11),sharex=True,sharey=True)
    for ci,ch in enumerate(sorted(set(a['channel'][rows]))):
        for rx in (0,1):
            ix=mask&(a['channel'][rows]==ch)&(a['receiver'][rows]==rx);ax=axes[ci,rx]
            ax.scatter(a['times_s'][rows[ix]],wrap(freq[ix])/1000,s=9,c='#555555',alpha=.7,lw=0)
            ax.set(title=f'RX{rx} · CH{ch} · {sum(ix):,} candidates',xlim=(0,300),ylim=(-period/2000,period/2000));ax.grid(alpha=.18)
            if rx==0:ax.set_ylabel('Wrapped CFO (kHz)')
            if ci==3:ax.set_xlabel('Receive time since capture start (s)')
    fig.suptitle(f'Scan A · db9243281 · {title}\n{sum(mask):,} / {len(rows):,} candidates · assigned AND unassigned included',fontsize=14)
    fig.text(.5,.015,'Same refined frequencies and axes in both figures. One dot per candidate, not per pair; overlapping points remain plotted.\nFilter uses frequency separation modulo 227.273 kHz within the same receiver/channel/probe—not orbit residual.\nNo consolidation, timing-similarity test, or membership changes.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.07,1,.93));fig.savefig(out/f'{name}.png',dpi=145);plt.close(fig)
(out/'receipt.json').write_text(json.dumps(summary,indent=2));print(json.dumps({k:v for k,v in summary.items() if k not in ('rows','sources')},indent=2))
