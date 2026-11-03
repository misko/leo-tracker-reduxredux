"""Frozen-state factor and derivative audit; no fit and no truth-based choice."""
import csv,json,sys
from pathlib import Path
from dataclasses import replace
import numpy as np
from objective import HERE,CONES,cones,GeometryObjective
sys.path.insert(0,str(CONES))
from experiment import loader,controls
from leo.contracts.regional_position import PositionScore

def main():
    theta,frames,support=cones.cone_bundle();out={'theta':theta.tolist(),'bundle_digests':cones.CONE_BUNDLE_DIGESTS,'fixed_states':[],'gradients':[]};markers=[]
    for case in ('1939','2139'):
        doc,old,obs,prior,bank,checkpoint,prefix=loader.load(case)
        primary=json.loads((CONES/case/'polished.json').read_text());score=replace(PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1.)
        for arm in controls.ARMS:
            selected=next(r for r in primary['selections'] if r['option']=='control' and r['arm']==arm);basin=selected['basin']
            assoc=checkpoint.get(prefix+':'+basin+':association')['result'];cal=checkpoint.get(prefix+':'+basin+':calibration')['result'];subset=bank.select(assoc['selected_indices']);v=np.asarray(selected['vector'])
            state={'case':case,'arm':arm,'basin':basin,'modes':{}}
            uniform=GeometryObjective(obs,subset,prior,score,receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']),mode='control');_,_,base_terms=uniform.evaluate(v)
            geometries={}
            for mode in ('conditional','absolute','absolute2'):
                obj=GeometryObjective(obs,subset,prior,score,receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']),mode=mode,theta=theta,frames=frames,support=support)
                value,g,terms=obj.evaluate(v);geom=obj.last_geometry;geometries[mode]=geom
                weights=base_terms.responsibilities
                state['modes'][mode]={'objective':value,'mean_row_q_mass':float(geom['q'].sum(axis=1).mean()),'base_mean_row_q_mass':float(geom['base_q'].sum(axis=1).mean()),'mean_clutter_posterior':float(terms.clutter_probability.mean()),'weighted_factor':float(np.sum(weights*geom['factor'])/weights.sum()),'signal_mass':float(terms.responsibilities.sum())}
                indices=[0,1,6,7,8,int(np.argmax(abs(g[8:])))+8]
                for j in dict.fromkeys(indices):
                    h=.001 if j<2 else 1e-5;plus=v.copy();minus=v.copy();plus[j]+=h;minus[j]-=h
                    numeric=(obj.evaluate(plus)[0]-obj.evaluate(minus)[0])/(2*h);err=abs(numeric-g[j])
                    assert err<max(.003,abs(g[j])*.0002),(case,arm,mode,j,g[j],numeric)
                    out['gradients'].append({'case':case,'arm':arm,'mode':mode,'index':j,'analytic':float(g[j]),'numeric':float(numeric),'absolute_error':float(err)})
            out['fixed_states'].append(state)
            geom=geometries['conditional'];unit=geom['unit_enu']
            for j,number in enumerate(subset.numbers):
                for rx in (0,1):
                    rows=obs.receiver==rx;w=base_terms.responsibilities[rows,j];mass=float(w.sum())
                    if not mass:continue
                    rec={'case':case,'arm':arm,'basin':basin,'number':int(number),'receiver':rx,'uniform_posterior_mass':mass,'posterior_mean_support':float(w@geom['support'][rows,j]/mass),'posterior_backface_fraction':float(w@(unit[rows,j]@frames[rx,2]<0)/mass),'posterior_opposite_az_half_fraction':float(w@(unit[rows,j,0]*(1 if rx==0 else -1)>0)/mass)}
                    for mode in geometries:rec[mode+'_mean_factor']=float(w@geometries[mode]['factor'][rows,j]/mass)
                    markers.append(rec)
    (HERE/'audit.json').write_text(json.dumps(out,indent=2))
    with (HERE/'fixed_state_factors.csv').open('w') as f:
        writer=csv.DictWriter(f,list(markers[0]));writer.writeheader();writer.writerows(markers)
    print(json.dumps(out['fixed_states'],indent=2));print('gradient checks',len(out['gradients']),'maxerror',max(x['absolute_error'] for x in out['gradients']))

if __name__=='__main__':main()
