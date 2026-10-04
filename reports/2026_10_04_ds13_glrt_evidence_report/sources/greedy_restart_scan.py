"""Count-first greedy restart over all canonical peaks and all archived IDs.

Development/in-sample diagnostic at known position. Clears all memberships,
retains existing fold-specific nuisance calibration. One common-relative timing
mode per satellite. Frozen mode pool, with available-peak/coherence updates after
every selection; no continuous nuisance refit or claim of global optimality.
"""
import argparse,csv,json,sys,time
from pathlib import Path
import numpy as np
from replay import ROOT,OLD,NAMESPACE,digest,corrected_prediction
from benchmark import SESSIONS,ALIAS_HZ
from gap_allfold_summary import location
from training_bootstrap import training_view
from adaptive_discovery import root_offsets,timing_modes

OUT=NAMESPACE/'greedy-restart-scan-A'
ARMS=('fitted-c','zero-c')

class FrozenCalibration:
    def __init__(self):
        sys.path.insert(0,str(OLD))
        from exhaustive_subset import load_expanded_scan,rf_features
        self.data=load_expanded_scan(SESSIONS['A']);self.parts=[]
        self.sources={str(Path(__file__)):digest(Path(__file__))};self.baseline={a:[] for a in ARMS}
        for fold in range(5):
            base=location(fold,'corrected');sp=base/'training-union'/f'fold-{fold}'/'A.json';dp=base/'heldout-decoding'/f'fold-{fold}'/'A.json'
            sel=json.loads(sp.read_text());dec=json.loads(dp.read_text());assert digest(sp)==dec['source_sha256']
            self.sources.update({str(p):digest(p) for p in (sp,dp)})
            mask=np.zeros(len(self.data.times),bool);mask[sel['original_test_rows']]=True
            d=training_view(self.data,mask);features=rf_features(d.rf,d.receiver,False)[1];models={}
            for arm in ARMS:
                folder=NAMESPACE/('gap-discovery' if fold==4 else 'gap-campaign/discovery')
                cp=folder/arm/'training-calibration'/f'fold-{fold}'/'A.json';mp=base/'training-discovery'/f'fold-{fold}'/arm/'A-proposals.json'
                c=json.loads(cp.read_text())['correction'];common=json.loads(mp.read_text())['common_timing_s'];model=sel['arms'][arm]
                correction=corrected_prediction(np.zeros(len(d.times)),d.times,d.receiver,c['nodes_s'],c['correction_knots_hz'])+features@np.array(model['coefficient'])
                models[arm]=(np.array(model['parameters']),common,correction)
                self.sources.update({str(p):digest(p) for p in (cp,mp)})
                self.baseline[arm].extend(dec['arms'][arm]['methods']['tracklet']['assignments'])
            self.parts.append((d,models))
        original=np.concatenate([d.original_rows for d,_ in self.parts])
        frozen=ROOT/'frozen/A-observations.npz';self.sources[str(frozen)]=digest(frozen)
        with np.load(frozen) as a:assert len(original)==len(set(original))==7382 and set(original)==set(a['canonical_rows'])
        mask=np.zeros(len(self.data.times),bool);mask[original]=True;self.d=training_view(self.data,mask)
        for name in ('times','measured','rf','receiver','channel','group','margin'):
            setattr(self.d,name,np.asarray(getattr(self.data,name))[original])
        self.d.original_rows=original

    def predict(self,arm,ids,offset):
        from prediction_jacobian import paired_prediction_jacobian
        pp=[];vv=[];rr=[]
        for d,models in self.parts:
            params,common,correction=models[arm];trial=params.copy();trial[6+ids]=common+offset
            rows=np.repeat(np.arange(len(d.times)),len(ids));sats=np.tile(ids,len(d.times))
            p,v,j=paired_prediction_jacobian(d,trial,rows,sats)
            pp.append(p.reshape(len(d.times),-1)+correction[:,None]);vv.append(v.reshape(len(d.times),-1));rr.append(j.tau.reshape(len(d.times),-1))
        return np.concatenate(pp),np.concatenate(vv),np.concatenate(rr)

    def residual(self,arm,index,offset):
        from exhaustive_subset import circular_residual
        p,v,r=self.predict(arm,np.array([index]),offset)
        return circular_residual(self.d.measured,p[:,0],ALIAS_HZ),v[:,0],r[:,0]


def evaluate(mode,used,groups,times,tolerance=600.,minimum=10,minspan=5.,maxgap=5.):
    """Closest currently free peak per satellite/probe, then lane coherence."""
    selected=[]
    for lane in mode['lanes']:
        rows,errors=lane
        ok=(abs(errors)<=tolerance)&~used[rows]
        order=np.flatnonzero(ok)
        # Lanes are already ordered by |residual|, so first probe occurrence wins.
        _,first=np.unique(groups[rows[order]],return_index=True);order=order[first]
        order=order[np.argsort(times[rows[order]],kind='stable')]
        for part in np.split(order,np.flatnonzero(np.diff(times[rows[order]])>maxgap)+1):
            if len(part)>=minimum and times[rows[part[-1]]]-times[rows[part[0]]]>=minspan:
                selected.extend((int(rows[i]),float(errors[i])) for i in part)
    # Primary objective is count; likelihood/prior proxy breaks exact count ties.
    count=len(selected);sse=sum(e*e for _,e in selected)
    return dict(count=count,score=-.5*sse/200**2-.5*mode['offset_s']**2,
        rms_hz=(sse/count)**.5 if count else None,rows=[r for r,e in selected],errors=[e for r,e in selected])


def compile_mode(record,receiver,channel):
    rows=np.array(record['eligible_rows'],int);errors=np.array(record['residual_hz'],float);lanes=[]
    for rx,ch in sorted(set(zip(receiver[rows].tolist(),channel[rows].tolist()))):
        ix=np.flatnonzero((receiver[rows]==rx)&(channel[rows]==ch));ix=ix[np.argsort(abs(errors[ix]),kind='stable')]
        lanes.append((rows[ix],errors[ix]))
    return dict(catalog_number=record['catalog_number'],offset_s=record['offset_s'],lanes=lanes,rows=rows)


def select(modes,groups,times,tolerance=600.,minimum=10,minspan=5.):
    used=np.zeros(len(groups),bool);chosen=set();trace=[];assignments=[]
    cache=[evaluate(m,used,groups,times,tolerance,minimum,minspan) for m in modes]
    standalone=[dict(catalog_number=m['catalog_number'],offset_s=m['offset_s'],count=c['count'],rms_hz=c['rms_hz']) for m,c in zip(modes,cache)]
    while True:
        available=[i for i,m in enumerate(modes) if m['catalog_number'] not in chosen and cache[i]['count']>0]
        if not available:break
        best=max(available,key=lambda i:(cache[i]['count'],cache[i]['score'],-modes[i]['catalog_number'],-i))
        m=modes[best];result=cache[best];rr=np.array(result['rows'],int)
        assert not used[rr].any();used[rr]=True;chosen.add(m['catalog_number'])
        trace.append(dict(step=len(trace)+1,catalog_number=m['catalog_number'],offset_s=m['offset_s'],added=result['count'],standalone=standalone[best]['count'],cumulative=int(used.sum()),rms_hz=result['rms_hz'],mode_index=best))
        assignments.extend(dict(row_index=r,catalog_number=m['catalog_number'],residual_hz=e,mode_index=best) for r,e in zip(result['rows'],result['errors']))
        for i,other in enumerate(modes):
            if other['catalog_number'] not in chosen and np.isin(other['rows'],rr).any():
                cache[i]=evaluate(other,used,groups,times,tolerance,minimum,minspan)
    assert len(assignments)==len({r['row_index'] for r in assignments})==len({(int(groups[r['row_index']]),r['catalog_number']) for r in assignments})
    return dict(trace=trace,assignments=assignments,standalone=standalone,assigned=len(assignments),selected_satellites=len(chosen),coverage=len(assignments)/len(groups))


def discover():
    started=time.monotonic();cal=FrozenCalibration();d=cal.d
    from exhaustive_subset import circular_residual
    OUT.mkdir(exist_ok=True);target=OUT/'candidate-pool.json'
    if target.exists():raise FileExistsError(target)
    records={a:[] for a in ARMS};inventory=[]
    for begin in range(0,len(d.numbers),16):
        ids=np.arange(begin,min(begin+16,len(d.numbers)));offsets={int(i):[] for i in ids}
        for arm in ARMS:
            votes=[[] for _ in ids];groups=[[] for _ in ids]
            for coarse in np.arange(-20.,20.001,1.):
                p,v,r=cal.predict(arm,ids,coarse);e=circular_residual(d.measured[:,None],p,ALIAS_HZ);root,ok=root_offsets(coarse,e,r,v)
                for j in range(len(ids)):
                    votes[j].extend(root[ok[:,j],j]);groups[j].extend(d.group[ok[:,j]])
            for j,index in enumerate(ids):
                for offset,support in timing_modes(votes[j],groups[j]):
                    for iteration in range(3):
                        e,v,r=cal.residual(arm,index,offset);near=v&(abs(e)<=600)
                        ix=np.flatnonzero(near);ix=ix[np.argsort(abs(e[ix]),kind='stable')]
                        _,first=np.unique(d.group[ix],return_index=True);ix=ix[first]
                        if len(ix)<10:break
                        step=(np.sum(r[ix]*e[ix])/200**2-offset)/(np.sum(r[ix]**2)/200**2+1.)
                        offset=float(np.clip(offset+np.clip(step,-.1,.1),-20,20))
                    offsets[int(index)].append(float(offset))
        # Both calibration arms use precisely the same union of timing hypotheses.
        for index in ids:
            union=sorted(set(offsets[int(index)]));inventory.append(dict(catalog_number=int(d.numbers[index]),timing_modes=len(union)))
            for offset in union:
                for arm in ARMS:
                    e,v,r=cal.residual(arm,index,offset);rr=np.flatnonzero(v&(abs(e)<=600))
                    records[arm].append(dict(catalog_number=int(d.numbers[index]),satellite_index=int(index),offset_s=offset,eligible_rows=rr.tolist(),residual_hz=e[rr].tolist()))
        print('DISCOVERY',int(ids[-1])+1,'/',len(d.numbers),'matched modes',len(records['fitted-c']),flush=True)
    assert [(m['catalog_number'],m['offset_s']) for m in records[ARMS[0]]]==[(m['catalog_number'],m['offset_s']) for m in records[ARMS[1]]]
    result=dict(scope=__doc__,scan=SESSIONS['A'],sources=cal.sources,inventory=inventory,arms=records,original_rows=d.original_rows.tolist(),baseline=cal.baseline,elapsed_s=time.monotonic()-started)
    with target.open('x') as f:json.dump(result,f)
    print('DISCOVERY COMPLETE',result['elapsed_s'],flush=True)


def run_selection():
    started=time.monotonic();source=OUT/'candidate-pool.json';pool=json.loads(source.read_text())
    for p,h in pool['sources'].items():assert digest(Path(p))==h
    with np.load(ROOT/'frozen/A-observations.npz') as a:
        orig=np.array(pool['original_rows']);groups=a['group'][orig];times=a['times_s'][orig];rx=a['receiver'][orig];ch=a['channel'][orig]
    results={};rows=[]
    for arm in ARMS:
        modes=[compile_mode(m,rx,ch) for m in pool['arms'][arm]];results[arm]={}
        for tolerance in (600.,300.,150.):
            r=select(modes,groups,times,tolerance);old={a['row_index']:a['catalog_number'] for a in pool['baseline'][arm]}
            for a in r['assignments']:a['row_index']=int(orig[a['row_index']])
            new={a['row_index']:a['catalog_number'] for a in r['assignments']}
            r.update(tolerance_hz=tolerance,baseline_count=len(old),new_vs_baseline=len(set(new)-set(old)),lost_vs_baseline=len(set(old)-set(new)),relabeled_vs_baseline=sum(new[i]!=old[i] for i in set(new)&set(old)))
            results[arm][str(int(tolerance))]=r
            rows.append(dict(arm=arm,tolerance_hz=int(tolerance),assigned=r['assigned'],unassigned=len(orig)-r['assigned'],coverage=r['coverage'],satellites=r['selected_satellites'],baseline=len(old),new=r['new_vs_baseline'],lost=r['lost_vs_baseline'],relabeled=r['relabeled_vs_baseline']))
            print(rows[-1],flush=True)
    with (OUT/'greedy-results.json').open('x') as f:json.dump(dict(scope=__doc__,source_sha256=digest(source),arms=results,elapsed_s=time.monotonic()-started),f)
    with (OUT/'comparison.csv').open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print('SELECTION COMPLETE',time.monotonic()-started,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['discover','select']);a=p.parse_args()
    discover() if a.stage=='discover' else run_selection()
