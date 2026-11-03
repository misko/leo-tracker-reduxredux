"""Truth-free RX-anchor initializer controls; same physical seed in every model."""
import json,time,hashlib
from pathlib import Path
from dataclasses import replace
import numpy as np
import experiment as previous
from objective import BackgroundObjective

HERE=Path(__file__).resolve().parent
MODELS={'independent':(0.,0.),'paired':(.9,0.),'background':(.9,.9)}

def anchored_clock_seeds(obs,base,vector,pairs):
    original=np.asarray(vector,float)
    _,meta=previous.clock_seed(obs,base,original,pairs)
    beta_a,beta_b=meta['differential_offset_hz'],meta['differential_slope_hz_s']
    rx0=original.copy();rx0[4]=rx0[2]+beta_a;rx0[5]=rx0[3]+beta_b
    rx1=original.copy();rx1[2]=rx1[4]-beta_a;rx1[3]=rx1[5]-beta_b
    return {'anchor-rx0':rx0,'anchor-rx1':rx1},meta

def main():
    from leo.analysis.regional_position_score import PositionObjective,coordinates
    from leo.analysis.regional_position_fit import fit_position
    from leo.contracts.regional_position import PositionScore
    target=HERE/'anchor_results.json'
    if target.exists():raise FileExistsError(target)
    begun=time.monotonic();out=dict(status='running',protocol_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),seconds_per_fit=20.,maximum_iterations=400,models=MODELS,cases=[])
    def save():target.with_name('anchor_progress.json').write_text(json.dumps(out,default=previous.controls.encode,indent=2))
    for case in ('1939','2139'):
        source=HERE/f'{case}.json';background=json.loads(source.read_text());assert background['status']=='complete'
        paired_path=HERE.parent/'paired_identity'/f'{case}.json';paired=json.loads(paired_path.read_text());assert paired['status']=='complete'
        doc,old,obs,prior,bank,cp,prefix=previous.loader.load(case);pairs=np.asarray(paired['pair_rows'])
        selected_basins=background['selected_basins'];assert len(selected_basins)==1
        basin=selected_basins[0];region=background['basins'][basin];center=np.asarray(region['center']);radius=region['radius_km']
        assoc=cp.get(prefix+':'+basin+':association')['result'];cal=cp.get(prefix+':'+basin+':calibration')['result'];subset=bank.select(assoc['selected_indices'])
        score=replace(PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1.)
        base=PositionObjective(obs,subset,prior,score,receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']))
        original_rows=[r for r in paired['candidates'] if r['option']=='paired' and r['basin']==basin and r['feasible']]
        original={arm:min((r for r in original_rows if r['arm']==arm),key=lambda r:r['selection_score']) for arm in previous.controls.ARMS}
        pool=[dict(r,source='previous-background') for r in background['candidates'] if r['basin']==basin and r['feasible']]
        pool += [dict(r,source='original-paired-with-retained-incumbents') for r in paired['candidates'] if r['basin']==basin and r['feasible']]
        unique={}
        for row in pool:unique.setdefault((row['arm'],previous.controls.vector_digest(row['vector'])),row)
        pool=list(unique.values());penalty=original['fitted-c']['calibration_penalty']
        minimum=max(-20.,subset.nodes_s[0]-obs.times_s.min());maximum=min(20.,subset.nodes_s[-1]-obs.times_s.max())
        result=dict(case=case,session_id=old['session_id'],basin=basin,center=center,radius_km=radius,scope='conditional previous paired-selected basin, all prior same-basin candidates retained',input_sha256=doc['input_manifest_sha256'],analysis_sha256=doc['analysis_manifest_sha256'],evidence_sha256=doc['evidence_sha256'],source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,paired_path,HERE/'objective.py',HERE/'experiment.py')},runs=[],candidates=[],selections=[],initializers={})
        out['cases'].append(result)
        seeds={}
        for arm in previous.controls.ARMS:
            seeds[arm],meta=anchored_clock_seeds(obs,base,original[arm]['vector'],pairs)
            result['initializers'][arm]=dict(original_vector=original[arm]['vector'],original_sha256=previous.controls.vector_digest(original[arm]['vector']),metadata=meta,anchors={anchor:dict(vector=v,vector_sha256=previous.controls.vector_digest(v),pair_clock=previous.clock_metrics(obs,base,v,pairs)) for anchor,v in seeds[arm].items()})
        for model,(rho,eta) in MODELS.items():
            objective=BackgroundObjective(obs,subset,prior,score,receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']),pairs=pairs,rho=rho,eta=eta)
            def record(v,arm,origin,**extra):
                value,g,t=objective.evaluate(np.asarray(v));background_diag=objective.last_background.copy();_,_,uniform=base.evaluate(np.asarray(v));mass=float(t.responsibilities.sum())
                return dict(model=model,rho=rho,eta=eta,arm=arm,basin=basin,origin=origin,vector=np.asarray(v),objective=value,selection_score=value+penalty,data_nll=t.nll,uniform_frequency_data_nll=uniform.nll,timing_penalty=value-t.nll,calibration_penalty=penalty,signal_fraction=mass/len(obs.window_ids),posterior_rms_hz=float(np.sqrt(np.sum(t.responsibilities*t.residual_hz**2)/mass)),mean_common_background_probability=float(np.mean(background_diag['common_background_probability'])),pair_clock=previous.clock_metrics(obs,base,v,pairs),**previous.controls.audit(v,g,objective.basis,arm,prior.radius_km,center,radius,minimum,maximum),**extra)
            for row in pool:
                r=record(row['vector'],row['arm'],'retained:'+row['source'])
                if r['feasible']:result['candidates'].append(r)
            for arm in previous.controls.ARMS:
                for anchor,seed in seeds[arm].items():
                    fit=fit_position(objective,seed,rf_arm=arm,maximum_seconds=20.,maximum_iterations=400,local_center=center,local_radius_km=radius)
                    row=record(fit.vector,arm,anchor,elapsed_s=fit.elapsed_s,stop_reason=fit.stop_reason,evaluations=fit.evaluations,seed_sha256=previous.controls.vector_digest(seed))
                    assert abs(row['objective']-fit.objective)<1e-6;assert abs(row['stationarity']-fit.stationarity)<1e-5
                    result['runs'].append(row)
                    if row['feasible']:result['candidates'].append(row)
                    print(case,model,arm,anchor,round(row['selection_score'],3),row['converged'],row['pair_clock'],flush=True);save()
            for arm in previous.controls.ARMS:
                result['selections'].append(min((r for r in result['candidates'] if r['model']==model and r['arm']==arm),key=lambda r:r['selection_score']))
        # Reference evaluation follows completion of score-only selection.
        for r in result['candidates']+result['selections']:
            lat,lon=np.radians(coordinates(prior,np.asarray(r['vector'])[:2]));a,b=np.radians([doc['reference_latitude_deg'],doc['reference_longitude_deg']]);h=np.sin((lat-a)/2)**2+np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2
            r['horizontal_error_m']=float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1))))
        save()
    out.update(status='complete',elapsed_s=time.monotonic()-begun,fit_elapsed_s=sum(r['elapsed_s'] for c in out['cases'] for r in c['runs']));save();target.write_text(json.dumps(out,default=previous.controls.encode,indent=2))

if __name__=='__main__':main()
