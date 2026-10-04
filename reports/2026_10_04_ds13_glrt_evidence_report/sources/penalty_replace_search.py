"""Greedy plus one-out/greedy-many-in under N_peaks - 10*N_satellites.

Fixed candidate timing pool and nuisance calibration. Coherent exclusive
assignments only; identity confidence is not certified. A complete no-improvement
pass establishes a fixed point only for this greedy-repair neighborhood.
"""
import argparse,json,time
from pathlib import Path
import numpy as np
from replay import ROOT,NAMESPACE,digest
from greedy_restart_scan import compile_mode,evaluate

OUT=NAMESPACE/'penalty10-replacement'

class Search:
    def __init__(self,modes,groups,times,penalty=10.,minimum=10,minspan=5.):
        self.modes=modes;self.groups=groups;self.times=times;self.penalty=penalty;self.minimum=minimum;self.minspan=minspan
        self.row_modes=[[] for _ in groups];self.catalog_modes={}
        for i,m in enumerate(modes):
            self.catalog_modes.setdefault(m['catalog_number'],[]).append(i)
            for r in m['rows']:self.row_modes[int(r)].append(i)

    def affected(self,rows):
        return set(i for r in rows for i in self.row_modes[int(r)])

    def evaluate(self,i,used):
        return evaluate(self.modes[i],used,self.groups,self.times,600.,self.minimum,self.minspan)

    def objective(self,chosen):
        return float(sum(v['count'] for v in chosen.values())-self.penalty*len(chosen))

    def refresh(self,indices,chosen,used,cache,forbidden=frozenset()):
        for i in indices:
            n=self.modes[i]['catalog_number']
            if n not in chosen and n not in forbidden:cache[i]=self.evaluate(i,used)

    def fill(self,chosen,used,cache,forbidden=frozenset()):
        additions=[]
        while True:
            candidates=[i for i,m in enumerate(self.modes) if m['catalog_number'] not in chosen and m['catalog_number'] not in forbidden and cache[i]['count']>self.penalty]
            if not candidates:break
            i=max(candidates,key=lambda j:(cache[j]['count'],cache[j]['score'],-self.modes[j]['catalog_number'],-j))
            n=self.modes[i]['catalog_number'];v=dict(cache[i],mode_index=i,catalog_number=n)
            assert not used[v['rows']].any();chosen[n]=v;used[v['rows']]=True
            additions.append(dict(catalog_number=n,mode_index=i,added=v['count'],marginal_score=v['count']-self.penalty,objective=self.objective(chosen)))
            self.refresh(self.affected(v['rows']),chosen,used,cache,forbidden)
        return additions

    def run(self,max_passes=3):
        started=time.monotonic();used=np.zeros(len(self.groups),bool);chosen={}
        cache=[self.evaluate(i,used) for i in range(len(self.modes))]
        initial_trace=self.fill(chosen,used,cache);initial=self.export(chosen)
        print('GREEDY',initial['assigned'],initial['satellites'],initial['objective'],flush=True)
        trials=[];passes=[];converged=False
        for sweep in range(max_passes):
            accepted=0;order=list(chosen)
            for ordinal,n in enumerate(order):
                if n not in chosen:continue
                old=chosen[n];before=self.objective(chosen);before_count=int(used.sum());before_satellites=len(chosen)
                trial={k:v for k,v in chosen.items() if k!=n};tu=used.copy();tu[old['rows']]=False;tc=cache.copy()
                forbidden={n};self.refresh(self.affected(old['rows']),trial,tu,tc,forbidden)
                additions=self.fill(trial,tu,tc,forbidden)
                candidate_score=self.objective(trial)
                entry=dict(pass_index=sweep+1,removed_for_trial=n,removed_peaks=old['count'],before_score=before,trial_score=candidate_score,accepted=candidate_score>before,
                    replacement_satellites=[a['catalog_number'] for a in additions],replacement_peaks=sum(a['added'] for a in additions))
                if entry['accepted']:
                    # After accepting a genuine replacement, the removed ID may
                    # return only if its remaining support pays its own penalty.
                    self.refresh(self.catalog_modes[n],trial,tu,tc)
                    extra=self.fill(trial,tu,tc)
                    entry.update(refill_satellites=[a['catalog_number'] for a in extra],before_assigned=before_count,after_assigned=int(tu.sum()),before_satellites=before_satellites,after_satellites=len(trial),after_score=self.objective(trial))
                    assert entry['after_score']>before
                    chosen,used,cache=trial,tu,tc;accepted+=1
                    print('ACCEPT',entry,flush=True)
                trials.append(entry)
                if (ordinal+1)%10==0:print('PASS',sweep+1,'tested',ordinal+1,'/',len(order),'score',self.objective(chosen),flush=True)
            passes.append(dict(pass_index=sweep+1,tested=sum(t['pass_index']==sweep+1 for t in trials),accepted=accepted,objective=self.objective(chosen),assigned=int(used.sum()),satellites=len(chosen)))
            print('PASS COMPLETE',passes[-1],flush=True)
            if not accepted:converged=True;break
        final=self.export(chosen)
        return dict(initial=initial,final=final,initial_trace=initial_trace,trials=trials,passes=passes,converged=converged,termination='no_improving_greedy_repair' if converged else 'pass_limit',elapsed_s=time.monotonic()-started)

    def export(self,chosen):
        assignments=[];selected=[]
        for n,v in chosen.items():
            m=self.modes[v['mode_index']]
            assignments.extend(dict(row_index=r,catalog_number=n,mode_index=v['mode_index'],residual_hz=e) for r,e in zip(v['rows'],v['errors']))
            selected.append(dict(catalog_number=n,mode_index=v['mode_index'],offset_s=m['offset_s'],count=v['count'],rms_hz=v['rms_hz']))
        assert len(assignments)==len({a['row_index'] for a in assignments})==len({(int(self.groups[a['row_index']]),a['catalog_number']) for a in assignments})
        for a in assignments:assert abs(a['residual_hz'])<=600
        return dict(assigned=len(assignments),satellites=len(chosen),objective=self.objective(chosen),assignments=assignments,selected=selected)


def main():
    p=argparse.ArgumentParser();p.add_argument('--scan',choices=['A','B'],required=True);p.add_argument('--arm',choices=['fitted-c','zero-c'],required=True);p.add_argument('--passes',type=int,default=3);args=p.parse_args()
    source=NAMESPACE/f'greedy-restart-scan-{args.scan}'/'candidate-pool.json';pool=json.loads(source.read_text())
    for path,h in pool['sources'].items():assert digest(Path(path))==h
    assert [(m['catalog_number'],m['offset_s']) for m in pool['arms']['fitted-c']]==[(m['catalog_number'],m['offset_s']) for m in pool['arms']['zero-c']]
    orig=np.array(pool['original_rows'])
    with np.load(ROOT/'frozen'/f'{args.scan}-observations.npz') as a:
        assert len(orig)==len(set(orig)) and set(orig)==set(a['canonical_rows'])
        groups=a['group'][orig];times=a['times_s'][orig];rx=a['receiver'][orig];ch=a['channel'][orig]
    modes=[compile_mode(r,rx,ch) for r in pool['arms'][args.arm]]
    result=Search(modes,groups,times).run(args.passes)
    for stage in ('initial','final'):
        for a in result[stage]['assignments']:a['row_index']=int(orig[a['row_index']])
        result[stage]['coverage']=result[stage]['assigned']/len(orig)
        result[stage]['unassigned']=len(orig)-result[stage]['assigned']
    result.update(scope=__doc__,scan=args.scan,scan_id=pool['scan'],arm=args.arm,denominator=len(orig),score='assigned_unique_peaks - 10 * selected_unique_satellites',penalty=10,tolerance_hz=600,source_sha256=digest(source),script_sha256=digest(Path(__file__)))
    OUT.mkdir(exist_ok=True)
    with (OUT/f'{args.scan}-{args.arm}.json').open('x') as f:json.dump(result,f,indent=2)
    print('DONE',args.scan,args.arm,{s:{k:v for k,v in result[s].items() if k not in ('assignments','selected')} for s in ('initial','final')},'converged',result['converged'],'seconds',result['elapsed_s'],flush=True)

if __name__=='__main__':main()
