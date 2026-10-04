"""Highest refined GLRT margin per original receiver/channel/probe; no 0.6 gate."""
import argparse,json
from pathlib import Path
import numpy as np
from solve_refined_scan_A import RefinedCalibration,SOURCE
from replay import NAMESPACE,ROOT,digest
from training_bootstrap import training_view
import greedy_pool_two_scans as g
from greedy_restart_scan import compile_mode,evaluate
from penalty_replace_search import Search

OUT=NAMESPACE/'full-scan-A-refinement/top-one'
def winners(records):
    groups={}
    for r in records:
        key=tuple(r['probe_key']);margin=r['refinement'].get('margin',r['original_margin'])
        priority=(margin,-r['row_index'])
        if key not in groups or priority>groups[key][0]:groups[key]=(priority,r['row_index'])
    return {v[1] for v in groups.values()}

class TopOneCalibration(RefinedCalibration):
    def __init__(self):
        super().__init__();keep=winners(json.loads(SOURCE.read_text())['records'])
        mask=np.isin(self.d.original_rows,list(keep));orig=self.d.original_rows[mask]
        self.d=training_view(self.d,mask);self.d.original_rows=orig
        parts=[]
        for d,models in self.parts:
            m=np.isin(d.original_rows,list(keep));orig=d.original_rows[m];view=training_view(d,m);view.original_rows=orig
            parts.append((view,{arm:(p,c,corr[m]) for arm,(p,c,corr) in models.items()}))
        self.parts=parts;assert set(self.d.original_rows)==keep
        assert len(set(self.d.group))==len(keep)==3837
        self.sources[str(Path(__file__))]=digest(Path(__file__))

def discover():
    g.SCAN='A';g.OUT=OUT;g.FrozenCalibration=TopOneCalibration;g.__doc__=__doc__;OUT.mkdir(exist_ok=True);g.discover()

def solve(arm):
    path=OUT/'candidate-pool.json';pool=json.loads(path.read_text())
    for p,h in pool['sources'].items():assert digest(Path(p))==h
    orig=np.array(pool['original_rows']);keep=winners(json.loads(SOURCE.read_text())['records']);assert set(orig)==keep
    assert [(m['catalog_number'],m['offset_s']) for m in pool['arms']['fitted-c']]==[(m['catalog_number'],m['offset_s']) for m in pool['arms']['zero-c']]
    with np.load(ROOT/'frozen/A-observations.npz') as a:groups=a['group'][orig];times=a['times_s'][orig];rx=a['receiver'][orig];ch=a['channel'][orig]
    modes=[compile_mode(m,rx,ch) for m in pool['arms'][arm]];r=Search(modes,groups,times).run(3)
    for stage in ('initial','final'):
        for x in r[stage]['assignments']:x['row_index']=int(orig[x['row_index']])
        r[stage].update(coverage=r[stage]['assigned']/len(orig),original_hypothesis_fraction=r[stage]['assigned']/7382,unassigned=len(orig)-r[stage]['assigned'])
    r.update(scope=__doc__,arm=arm,denominator=len(orig),source_sha256=digest(path),timing='One absolute satellite shift within +/-20 s; frozen RX/RF calibration',score='assigned - 10 * satellites')
    with (OUT/f'{arm}.json').open('x') as f:json.dump(r,f,indent=2)
    print('DONE',arm,{k:v for k,v in r['final'].items() if k not in ('assignments','selected')},flush=True)

def audit():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from candidate_guided_refinement import circular
    cal=TopOneCalibration();d=cal.d;lookup={int(r):i for i,r in enumerate(d.original_rows)}
    pool=json.loads((OUT/'candidate-pool.json').read_text());metrics=[]
    for arm in ('fitted-c','zero-c'):
        r=json.loads((OUT/f'{arm}.json').read_text());f=r['final'];aa=f['assignments'];assert len(aa)==f['assigned']==len({x['row_index'] for x in aa})
        assert len(aa)==len({int(d.group[lookup[x['row_index']]]) for x in aa})
        assert f['objective']==f['assigned']-10*f['satellites']
        for m in f['selected']:
            raw=pool['arms'][arm][m['mode_index']];chosen=[x for x in aa if x['catalog_number']==m['catalog_number']];ix=np.array([lookup[x['row_index']] for x in chosen])
            e,v,_=cal.residual(arm,raw['satellite_index'],raw['offset_s']);assert np.all(v[ix]) and np.all(abs(e[ix])<=600)
            assert np.allclose(e[ix],[x['residual_hz'] for x in chosen],atol=1e-6,rtol=0)
            used=np.ones(len(d.times),bool);used[ix]=False
            assert set(evaluate(compile_mode(raw,d.receiver,d.channel),used,d.group,d.times)['rows'])==set(ix)
        old=json.loads((NAMESPACE/'full-scan-A-refinement/solver'/f'A-{arm}.json').read_text())['final'];oldret=[x for x in old['assignments'] if x['row_index'] in lookup]
        metric=dict(arm=arm,assigned=f['assigned'],coverage=f['coverage'],unassigned=f['unassigned'],satellites=f['satellites'],score=f['objective'],converged=r['converged'],greedy_assigned=r['initial']['assigned'],replacement_gain=f['objective']-r['initial']['objective'],original_fraction=f['original_hypothesis_fraction'],previous_assigned=old['assigned'],previous_assigned_surviving_filter=len(oldret),previous_assignments_dropped=old['assigned']-len(oldret))
        metrics.append(metric);print(metric,flush=True)
        owned=np.array([int(i) in {x['row_index'] for x in aa} for i in d.original_rows])
        fig,axes=plt.subplots(4,2,figsize=(14,11),sharex=True,sharey=True)
        for ci,ch in enumerate(sorted(set(d.channel))):
            for rx in (0,1):
                ax=axes[ci,rx];lane=(d.channel==ch)&(d.receiver==rx)
                for isassigned,color,label in [(False,'#888888','Unassigned'),(True,'#0072b2','Assigned')]:
                    mask=lane&(owned==isassigned);ax.scatter(d.times[mask],circular(d.measured[mask])/1000,s=11,c=color,label=label)
                ax.set(title=f'RX{rx} · CH{ch} · {sum(lane&owned)}/{sum(lane)} assigned',xlim=(0,300),ylim=(-114,114));ax.grid(alpha=.15)
                if rx==0:ax.set_ylabel('Wrapped CFO (kHz)')
                if ci==3:ax.set_xlabel('Receive time (s)')
        axes[0,0].legend(fontsize=9)
        fig.suptitle(f'Scan A · highest GLRT margin per 20 ms probe · {arm}\n{f["assigned"]}/{len(d.times)} assigned ({f["coverage"]:.1%}) · {f["satellites"]} satellites')
        fig.text(.5,.012,'No 0.6 cutoff. One winner per receiver/channel/probe, selected without orbit information.\nSame penalty-10 greedy + replacement solver; frozen calibration. Raw in-sample association, not identity-certified.',ha='center',fontsize=9)
        fig.tight_layout(rect=(0,.055,1,.94));fig.savefig(OUT/f'{arm}-assignments.png',dpi=145);plt.close(fig)
    (OUT/'audit.json').write_text(json.dumps(dict(status='passed',retained=3837,original=7382,discarded=3545,metrics=metrics),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['discover','solve','audit']);p.add_argument('--arm',choices=['fitted-c','zero-c']);a=p.parse_args()
    if a.stage=='discover':discover()
    elif a.stage=='solve':solve(a.arm)
    else:audit()
