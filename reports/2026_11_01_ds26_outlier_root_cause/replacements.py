"""Bounded RF-nominated family replacement controls, diagnostic only."""
import argparse,copy
import numpy as np
from diagnose import ROOT,INPUT,ARMS,read,write,reconstruct,build,refit,objective
from family_debug import SUSPECT
from probe_algo03_feasible_recovery import gate_slacks
from audit_explicit_phase_endpoint import exact_gate_replay

def run(case,expand=False):
    out=ROOT/case;z=read(INPUT/(case+'.json'));d=reconstruct(z);n=SUSPECT[case];f=read(out/'family_diagnostic.json')
    nominees=set()
    for arm in ARMS:
        rows=sorted([r for r in f['results'] if r['arm']==arm and r['regime']=='causal' and r['calibration']=='family_omitted' and r['split']=='all' and r['level']=='small_rate'],key=lambda r:r['score'])
        nominees.update(r['norad'] for r in rows[:2] if r['norad']!=n)
    # This is a fixed small competitor set nominated by RF scores, never GPS.
    for new in sorted(nominees):
        target=out/f'replace_{n}_with_{new}{"_expanded" if expand else ""}.json'
        if target.exists():continue
        jold=list(d['scan'].norads).index(n)
        missing=new not in d['scan'].norads
        if missing and not expand:write(target,dict(status='candidate_absent_from_original_inference_bank',norad=new));continue
        if expand and not missing:continue
        dd=dict(d,node=copy.deepcopy(d['node']),entries=copy.deepcopy(d['entries']),problems={});oldp=d['problems']['fitted_c'][0]
        if missing:
            from sgp4.api import Satrec
            from leo.sky.propagation import ElementSetCatalogue
            from analyze_dsx01_fixed_site import ecef_states
            record=read(out/'tle-ledger.json')['causal'][str(new)];scan=copy.copy(d['scan']);jnew=len(scan.norads)
            cat=ElementSetCatalogue((str(new),),(new,),(Satrec.twoline2rv(*record['lines']),))
            pos,vel,good=ecef_states(cat,scan.receipt['origin_utc_ns'],scan.sky['time_s'])
            if not good.all():raise ValueError('new causal candidate propagation failed')
            scan.norads=np.r_[scan.norads,new]
            scan.sky=dict(scan.sky,position_km=np.concatenate([scan.sky['position_km'],pos]),velocity_km_s=np.concatenate([scan.sky['velocity_km_s'],vel]),phase_sigma_s=np.r_[scan.sky['phase_sigma_s'],1.])
            scan.elements=dict(scan.elements,**{str(new):dict(lines=record['lines'],provenance={k:v for k,v in record.items() if k!='lines'})})
            dd['scan']=scan;dd['node']['seed']['state']['phases']=np.r_[dd['node']['seed']['state']['phases'],0.]
        else:jnew=list(d['scan'].norads).index(new)
        nominee=next(r for r in f['results'] if r['arm']=='fitted_c' and r['regime']=='causal' and r['calibration']=='family_omitted' and r['split']=='all' and r['level']=='small_rate' and r['norad']==new)
        aliases={t['key']:int(a) for t,a in zip(f['tracks'],nominee['aliases'])}
        for row in dd['node']['seed']['rows']:
            if row['candidate_norad']==n:row.update(candidate_norad=new,candidate_index=jnew)
        for k,row in enumerate(oldp.rows):
            if row['component'] in aliases:dd['node']['aliases'][k]=aliases[row['component']]
        for e in dd['entries']:
            if e['norad']==n:e.update(norad=new,candidate_index=jnew)
        newlabels=sorted((set(oldp.labels)-{jold})|{jnew});oldmeans=dict(zip(oldp.labels,d['means']))
        dd['means']=np.array([oldmeans.get(j,0.) for j in newlabels])
        for arm in ARMS:
            p,x=d['problems'][arm];dd['problems'][arm]=(p,x)
            oldrefs=dict(zip(p.labels,p.reference));reference=np.array([oldrefs.get(j,nominee['phase_s'] if j==jnew else 0.) for j in newlabels])
            q,_=build(dd,z,arm,reference);dd['problems'][arm]=(q,x)
        pair={}
        cavity=read(out/(f'extended_omit_{n}.json' if (out/f'extended_omit_{n}.json').exists() else f'omit_{n}.json'))
        for arm in ARMS:
            r=refit(dd,z,arm,np.array(cavity[arm]['x']),rounds=10)
            p,ddd=build(dd,z,arm,np.array(r['reference']));x=np.array(r['x']);slacks=gate_slacks(p,x,ddd['entries'])
            p.explicit_phase_family=jnew;exact=exact_gate_replay(p,x,ddd['entries']);del p.explicit_phase_family
            r.update(failed_gates={k:v for k,v in slacks.items() if v<0},exact_replacement_gate_pass=exact['all_pass'],
                exact_maximum_linearization_difference_hz=exact['maximum_linearization_difference_hz'])
            pair[arm]=r;print(case,'replace',n,new,arm,round(r['error_m'],1),round(r['objective'],1),len(r['failed_gates']),flush=True)
        write(target,dict(status='diagnostic_complete',old=n,new=new,arms=pair,
            nomination='top two causal family-omitted RF scores union across c arms, same candidate sets; no evaluation coordinate',
            new_label_phase_mean='preserve original mean if label already present; zero otherwise',
            no_production_change=True,observations_retained=True,aliases=aliases,expanded_causal_catalogue=missing,
            new_tle_age_h=record['age_s']/3600 if missing else None))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('case');p.add_argument('--expand',action='store_true');a=p.parse_args();run(a.case,a.expand)
