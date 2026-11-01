"""Fixed diagnostics for every accepted population-study replacement.

These tests cannot change the frozen acceptance decision.
"""
import argparse
import copy
import time
import numpy as np
import evaluate as e
from transfer import gaussian_predict
from ds23_height_problem import geometry_features
from probe_ds23_history_calibrated_phase import make_problem


def selected_context(case,method):
    e.rec.CATALOGUES=e.ROOTS[case[:4]]/'catalogues'
    d,z,replay=e.load_case(case);result=e.read(e.OUT/case/'result.json');name=result['methods'][method]['selected']
    if not name:return d,z,None,None
    if name=='complete_history':
        dd,_=e.complete_history(d,z,case,e.active_ids(d),e.OUT/case/'incumbent_history')
        return dd,z,result['history_records'][0],d
    record=next(r for r in result['records'][method] if r['name']==name and r['accepted'])
    dd=d
    if method=='combined':
        dd,_=e.complete_history(dd,z,case,e.active_ids(dd),e.OUT/case/'incumbent_history')
        folder=e.OUT/case/str(record['target'])/(name+'-'+method)/'history'
        dd,_=e.complete_history(dd,z,case,set(record['hypothesis']['mapping'].values()),folder)
    return e.remap(dd,z,case,record['hypothesis']),z,record,d


def transfer(context,z,n,point,arm,mode='receiver'):
    reference=np.clip(context['means'],-30,30);p,_=e.build(context,z,arm,reference)
    c=p.calculate(point);begin=p.hardware.shape[1]+p.smooth.shape[1]
    mean=np.zeros(c['features'].shape[1]);mean[begin:begin+len(p.labels)]=context['means']/p.phase_sigma
    target=np.zeros(len(p.values),bool);rx=np.zeros(len(p.values),int);components=np.empty(len(p.values),object)
    for r,i,sl in zip(p.rows,p.members,p.slices):
        target[sl]=r['candidate_norad']==n;rx[sl]=p.scan.tracks[i]['receiver'];components[sl]=r['component']
    scale=np.ones(c['features'].shape[1]);scale[-len(p.members):]=.3;rows=[]
    selectors=rx if mode=='receiver' else components
    for label in sorted(set(selectors[p.keep&target])):
        test=p.keep&target&(selectors==label);train=p.keep&~test
        receiver=int(rx[test][0])
        if sum(p.keep&target&~test)<10 or sum(test)<5:continue
        p.reference=reference.copy()
        try:
            for step in range(20):
                geometry=geometry_features(p,point,0.)
                raw=p.values-p.q*geometry['intercept']-geometry['features']@mean
                fit=gaussian_predict(raw,geometry['features']*scale,train,test,powers=context['powers'][p.noise_groups])
                phase=(fit['posterior_coefficient']*scale+mean)[begin:begin+len(p.labels)]*p.phase_sigma
                change=float(max(abs(phase-p.reference)))
                if change<=.01 or step==19:break
                p.reference=.5*p.reference+.5*np.clip(phase,-30,30)
            fit.pop('posterior_coefficient')
            rows.append(dict(receiver=receiver,split=str(label),arm=arm,status='complete',held_points=int(sum(test)),
                phase_closed=change<=.01,phase_change_s=change,outside_window=bool(np.any(abs(phase)>30)),**fit))
        except Exception as exc:rows.append(dict(receiver=receiver,split=str(label),arm=arm,status='failed',reason=repr(exc)))
    return rows


def run(case):
    out=e.OUT/case/'diagnostics';out.mkdir(exist_ok=True);result=e.read(e.OUT/case/'result.json');reports=[]
    for method in ('history_only','reassociation_only','combined'):
        if result['methods'][method]['selected'] is None:continue
        path=out/(method+'.json')
        if path.exists():reports.append(e.read(path));continue
        if method=='combined' and result['methods'][method]['selected']=='complete_history' and (out/'history_only.json').exists():
            report=dict(e.read(out/'history_only.json'),method=method,reused_identical_history_only_diagnostic=True)
            e.write(path,report);reports.append(report);continue
        dd,z,record,d=selected_context(case,method);native=[];transfers=[];sensitivity=[]
        if record['name']!='complete_history':
            n=record['target'];new=record['hypothesis']['norad']
            screen=e.read(e.OUT/case/str(n)/'screen.json')
            for a in e.ARMS:
                point=np.asarray(screen['cavity'][a]['x'])
                for name,context,num in [('incumbent',d,n),('replacement',dd,new)]:
                    transfers += [dict(context=name,norad=num,**r) for r in transfer(context,z,num,point,a)]
                p,x=d['problems'][a];c=p.calculate(x)
                old={r['component']:c['conditional_residual_hz'][sl][p.keep[sl]] for r,sl in zip(p.rows,p.slices)}
                for tr in record['pair'][a]['tracks']:
                    if tr['norad']!=new:continue
                    times=np.asarray(tr['times_s']);res=np.asarray(tr['residual_hz'])
                    native.append(dict(arm=a,old_residual_hz=old[tr['component']],
                        before=e.diagnose.residual_stats(times,old[tr['component']]),after=e.diagnose.residual_stats(times,res),**tr))
        original=e.previous.feasible_fit
        starts={'selected_fitted':np.asarray(result['methods'][method]['final']['fitted_c']['x'])}
        for setting,margin in [('margin_001',.01),('margin_005',.05),('receiver50',0.)]:
            ctx=dd
            if setting=='receiver50':
                ctx=dict(dd,problem_factory=e.rec.ex.prior_factory(dd.get('problem_factory',make_problem),'04_receiver_shrink'))
            if margin:e.previous.feasible_fit=lambda fun,slacks,*args,**kwargs:original(fun,lambda x:np.asarray(slacks(x))-margin,*args,**kwargs)
            else:e.previous.feasible_fit=original
            rows=e.fit_rows(ctx,z,starts,set(record.get('hypothesis',{}).get('allowed_families',[])),out/(method+'-'+setting+'-fits.json'))
            for r in rows:
                row=dict(method=setting,arm=r['arm'],status=r['status'],qualified=r['qualified'],error_m=r.get('error_m'),objective=r.get('objective'),reason=r.get('reason'))
                if r['status']=='complete':
                    p,ctx1=e.build(ctx,z,r['arm'],np.asarray(r['reference']));slacks=e.rec.ex.gate_slacks(p,np.asarray(r['x']),ctx1['entries'])
                    row.update(minimum_slack=float(min(slacks.values())),margin_pass=min(slacks.values())>=margin-1e-5,
                        displacement_km=float(np.linalg.norm(np.asarray(r['x'])-np.asarray(result['methods'][method]['final'][r['arm']]['x']))))
                sensitivity.append(row)
        e.previous.feasible_fit=original
        report=dict(case=case,method=method,selected=record['name'],native=native,transfer=transfers,sensitivity=sensitivity,
            scope='Conditional cross-receiver prediction, training-only phase refresh, inherited graph/alias choices; fixed family-omitted RF position; no independent catalogue-discovery claim')
        e.write(path,report);reports.append(report)
    e.write(out/'result.json',reports)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('case');run(p.parse_args().case)
