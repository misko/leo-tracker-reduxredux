"""Preserved failure audit: propagation padding and shared-identity merge.

These supplementary diagnostics never change the frozen joint result.
"""
import sys
import time
from pathlib import Path
import numpy as np
import joint as j


def expanded(d,z):
    view=j.ev.position.prediction_scan(d['scan'],30)
    dd=dict(d,scan=view,problems=dict(d['problems']))
    replay={}
    for a,(old,x) in d['problems'].items():
        new,_=j.ev.build(dd,z,a,old.reference)
        delta=j.ev.objective(new,dd,x)-j.ev.objective(old,d,x)
        if abs(delta)>1e-4:raise ValueError('Expanded baseline mismatch '+repr(delta))
        dd['problems'][a]=(new,x);replay[a]=delta
    return dd,replay


def run(case):
    out=j.OUT/case/'supplement';out.mkdir(exist_ok=True)
    protocol=out/'protocol.json'
    if protocol.exists():raise RuntimeError('Supplementary attempt already exists')
    j.write(protocol,dict(code_sha256=j.sha(__file__),frozen_ns=time.time_ns(),
        scope='Diagnostic only, no change to frozen result or acceptance',
        padding='same causal elements, integer knot grid extended from [-17,317] to [-40,340]; same original likelihood at original phases required',
        fit='15 phase rounds,40 position iterations, c0/fitted-c; same published and joint-source-family-omitted fitted-c starts and controls',
        merge='only previously excluded Cartesian nominees; one shared phase/orbit prior per existing identity, source native points preserved; no posthoc adoption'))
    j.rec.CATALOGUES=j.ev.ROOTS[case[:4]]/'catalogues'
    d,z,replay=j.ev.load_case(case);z=dict(z,case=case);dd,padding=expanded(d,z)
    j.write(out/'padding_replay.json',padding)
    targets=j.read(j.OUT/'protocol.json')['cases'][case]['targets']
    screens={n:j.read(j.SEALED/case/str(n)/'screen.json') for n in targets}
    pairs,_=j.pair_rule(targets,screens,set(targets))
    j.write(out/'hypotheses.json',pairs)
    baseline=j.read(j.OUT/case/'baseline.json')
    if (j.OUT/case/'starts.json').exists():starts=j.read(j.OUT/case/'starts.json')
    else:
        cav=j.rec.refit(j.omitted(dd,targets),z,'fitted_c',d['problems']['fitted_c'][1],rounds=15)
        j.write(out/'joint_source_cavity.json',cav)
        starts=dict(published=d['problems']['fitted_c'][1],joint_omitted=cav['x'])
    j.write(out/'starts.json',starts)
    control=j.ev.fit_rows(dd,z,starts,set(),out/'control_fits.json')
    records=[]
    for h in pairs:
        trial=out/h['name'];trial.mkdir(exist_ok=True)
        candidate=j.ev.remap(dd,z,case,h)
        rows=j.ev.fit_rows(candidate,z,starts,set(targets),trial/'fits.json')
        records.append(dict(name=h['name'],complete=sum(r['status']=='complete' for r in rows),
            qualified={a:sum(r['arm']==a and r['qualified'] for r in rows) for a in j.ARMS},
            fit_path=str(trial/'fits.json'),accepted=False,reason='supplementary diagnostic, never eligible for adoption'))
        print(case,h['name'],records[-1],flush=True)
    j.write(out/'result.json',dict(case=case,records=records,production_changed=False,accepted=False))


def overlap_audit(case):
    out=j.OUT/case/'merge_audit';out.mkdir(exist_ok=True)
    j.rec.CATALOGUES=j.ev.ROOTS[case[:4]]/'catalogues';d,z,_=j.ev.load_case(case)
    targets=j.read(j.OUT/'protocol.json')['cases'][case]['targets'];screens={n:j.read(j.SEALED/case/str(n)/'screen.json') for n in targets}
    pairs,_=j.pair_rule(targets,screens,set(targets));selected=pairs[0]
    records=[];curves=[]
    for a,(p,x) in d['problems'].items():
        state=p.state(x);calc=p.calculate(x)
        for source,destination in zip(targets,selected['destinations']):
            sources=[];destinations=[]
            for row,i,s in zip(p.rows,p.members,p.slices):
                n=row['candidate_norad'];u=p.keep[s]
                if n not in [source,destination] or not u.any():continue
                t=p.scan.tracks[i];rr=calc['conditional_residual_hz'][s][u];tt=t['times'][u]
                item=dict(arm=a,norad=n,component=row['component'],receiver=t['receiver'],channel=t['channel'],
                    count=int(sum(u)),start_s=float(min(tt)),end_s=float(max(tt)),phase_s=float(state['phases'][row['candidate_index']]),
                    residual=j.ev.diagnose.residual_stats(tt,rr),native_ids=[o for o,v in zip(t['observation_ids'],u) if v])
                (sources if n==source else destinations).append(item)
                curves.append(dict(**item,times_s=tt,values_hz=t['values'][u],residual_hz=rr))
            overlap=[]
            for s in sources:
                for t in destinations:
                    seconds=max(0,min(s['end_s'],t['end_s'])-max(s['start_s'],t['start_s']))
                    if seconds>0:overlap.append(dict(source=s['component'],destination=t['component'],seconds=seconds,
                        same_receiver=s['receiver']==t['receiver'],same_channel=s['channel']==t['channel']))
            source_ids={o for t in sources for o in t['native_ids']};destination_ids={o for t in destinations for o in t['native_ids']}
            records.append(dict(arm=a,source=source,destination=destination,sources=sources,destinations=destinations,
                duplicate_native_ids=sorted(source_ids&destination_ids),overlaps=overlap,
                interpretation='Different-band temporal overlap is compatible with a single satellite; separate baseline phase values do not establish distinct identity. A valid merge must pool all evidence once under one shared phase/orbit prior.'))
    j.write(out/'audit.json',records);j.write(out/'curves.json',curves)


if __name__=='__main__':
    overlap_audit(sys.argv[2]) if sys.argv[1]=='audit' else run(sys.argv[1])
