"""Independent read-only receipt verification. No optimization or inference fits."""
import hashlib,importlib.util,json
from dataclasses import replace
from pathlib import Path
import numpy as np
from leo.analysis.regional_position_score import PositionObjective,circular,coordinates
from leo.contracts.regional_position import PositionScore

HERE=Path(__file__).resolve().parent;PARENT=HERE.parent;REPORTS=PARENT.parent
def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
oracle=load_module('verification_public_loader',REPORTS/'2026_10_07_sigma1_root_cause/oracle.py')
controls=oracle.CONTROLS
identity=load_module('verification_identity_model',PARENT/'paired_identity/objective.py')
background=load_module('verification_background_model',PARENT/'paired_background/objective.py')

def clock(obs,obj,vector,pairs):
    left,right=pairs.T;nuisance=obj.design@vector[2:7]+obj.baseline
    residual=circular(obs.measured_hz[right]-obs.measured_hz[left]-nuisance[right]+nuisance[left]);center=float(np.median(residual));residual=center+circular(residual-center)
    times=(obs.times_s[left]+obs.times_s[right])/2;centered=times-times.mean()
    x=np.column_stack([*[(obs.channel[left]==c) for c in np.unique(obs.channel[left])],centered]);beta=np.linalg.lstsq(x,np.full(len(residual),center),rcond=None)[0]
    for _ in range(60):
        weights=np.minimum(1.,100/np.maximum(abs(residual-x@beta),1e-12));new=np.linalg.lstsq(x*np.sqrt(weights[:,None]),residual*np.sqrt(weights),rcond=None)[0]
        if np.max(abs(new-beta))<1e-8:beta=new;break
        beta=new
    return {'count':len(pairs),'median_absolute_residual_hz':float(np.median(abs(residual))),'p90_absolute_residual_hz':float(np.quantile(abs(residual),.9)),'robust_residual_slope_hz_s':float(beta[-1]),'channel_offsets_hz':beta[:-1].tolist()}

def main():
    output={'selected':[],'receipts':[],'checks':[],'limitations':[]};pair_path=PARENT/'identity/paired_topone.json';pairs_doc=json.loads(pair_path.read_text())
    output['paired_input_sha256']='sha256:'+hashlib.sha256(pair_path.read_bytes()).hexdigest()
    for case in ('1939','2139'):
        doc,old,obs,prior,bank,cp,prefix=oracle.load(case)
        admitted=pairs_doc['cases'][case]['100ns']['rows'];pairs=np.array([[r['row0'],r['row1']] for r in admitted])
        assert len(np.unique(pairs))==pairs.size
        for r,(i,j) in zip(admitted,pairs,strict=True):
            assert abs(r['epoch_difference_ns'])<=100 and obs.receiver[i]==0 and obs.receiver[j]==1
            assert obs.rf_hz[i]==obs.rf_hz[j]==r['rf_hz'] and obs.measured_hz[i]==r['cfo0_hz'] and obs.measured_hz[j]==r['cfo1_hz']
        score=replace(PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1.)
        for family in ('annealing','paired_identity','paired_background'):
            path=PARENT/family/f'{case}.json'
            if not path.exists():output['limitations'].append(f'{family}/{case}: absent');continue
            receipt=json.loads(path.read_text())
            if receipt['status']!='complete':output['limitations'].append(f'{family}/{case}: {receipt["status"]}, not audited as complete');continue
            mismatches=[str(p) for p,h in receipt['source_hashes'].items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
            assert receipt['evidence_sha256']==doc['evidence_sha256']
            if 'pair_rows' in receipt:assert receipt['pair_rows']==pairs.tolist()
            if family=='annealing':
                assert sum(x[1] for x in receipt['options']['control'])==sum(x[1] for x in receipt['options']['anneal'])==40
                for basin in receipt['selected_basins']:
                    for arm in controls.ARMS:
                        rows=[r for r in receipt['runs'] if r['basin']==basin and r['arm']==arm]
                        first_control=next(r for r in rows if r['option']=='control')
                        first_anneal=next(r for r in rows if r['option']=='anneal')
                        assert first_control['seed_sha256']==first_anneal['seed_sha256']
                        assert first_control['seed_sha256']==receipt['seeds'][basin][arm]['vector_sha256']
                output['checks'].append(f'{family}/{case}: 40 s matched schedules, own-arm first seeds identical; stage convergence repriced under final 125 Hz objective')
            else:
                for basin in receipt['basins']:
                    for arm in controls.ARMS:
                        origins=('primary',) if family=='paired_identity' else ('own-state','paired-clock')
                        for origin in origins:
                            rows=[r for r in receipt['runs'] if r['basin']==basin and r['arm']==arm and r['origin']==origin]
                            assert len(rows)==2 and len({r['seed_sha256'] for r in rows})==1
                output['checks'].append(f'{family}/{case}: all options share each own-arm primary seed; pair admission blind to orbit and frequency residual')
            for selected in receipt['selections']:
                option,arm,basin=selected['option'],selected['arm'],selected['basin'];v=np.asarray(selected['vector'])
                assert selected['selection_score']==min(r['selection_score'] for r in receipt['candidates'] if r['option']==option and r['arm']==arm)
                region=old['basins'][basin];center=np.asarray(region['center']);radius=region['radius_km'] if case=='1939' else max(25,2*region['radius_km'])
                assoc=cp.get(prefix+':'+basin+':association')['result'];cal=cp.get(prefix+':'+basin+':calibration')['result'];subset=bank.select(assoc['selected_indices']);baseline=np.asarray(cal['receiver_baseline_hz'])
                if family=='annealing':obj=PositionObjective(obs,subset,prior,score,receiver_baseline_hz=baseline)
                elif family=='paired_identity':obj=identity.PairedObjective(obs,subset,prior,score,receiver_baseline_hz=baseline,pairs=pairs,rho=0 if option=='control' else receipt['rho'])
                else:
                    obj=background.BackgroundObjective(obs,subset,prior,score,receiver_baseline_hz=baseline,pairs=pairs,rho=receipt['rho'],eta=0 if option=='control' else receipt['eta'])
                value,g,terms=obj.evaluate(v);audit=controls.audit(v,g,obj.basis,arm,prior.radius_km,center,radius,max(-20.,subset.nodes_s[0]-obs.times_s.min()),min(20.,subset.nodes_s[-1]-obs.times_s.max()))
                assert abs(value-selected['objective'])<1e-6 and abs(audit['stationarity']-selected['stationarity'])<1e-5
                assert audit['converged']==selected['converged'] and audit['feasible']
                if arm=='zero-c':assert v[6]==0
                lat,lon=np.radians(coordinates(prior,v[:2]));a,b=np.radians([doc['reference_latitude_deg'],doc['reference_longitude_deg']]);h=np.sin((lat-a)/2)**2+np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2;error=float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1))))
                assert abs(error-selected['horizontal_error_m'])<1e-5
                clock_metrics=clock(obs,obj,v,pairs)
                if 'pair_clock' in selected:
                    for k in ('median_absolute_residual_hz','p90_absolute_residual_hz','robust_residual_slope_hz_s'):assert abs(clock_metrics[k]-selected['pair_clock'][k])<1e-6
                output['selected'].append({'case':case,'family':family,'option':option,'arm':arm,'error_m':error,'selection_score':selected['selection_score'],'origin':selected['origin'],'incumbent_fallback':selected['origin'].startswith(('saved:','prior-paired')),'independent_audit':audit,'clock':clock_metrics})
            gradient_checks=receipt.get('gradient_checks',[])
            output['receipts'].append({'case':case,'family':family,'source_hash_mismatches':mismatches,'receipt_sha256':controls.digest_bytes(path.read_bytes()),'runs':len(receipt['runs']),'gradient_checks':len(gradient_checks),'maximum_gradient_error':max((r['absolute_error'] for r in gradient_checks),default=None)})
    output['nested_gaps']=[]
    for case in ('1939','2139'):
        for family in ('annealing','paired_identity','paired_background'):
            rows=[r for r in output['selected'] if r['case']==case and r['family']==family]
            for option in sorted({r['option'] for r in rows}):
                free=next(r for r in rows if r['option']==option and r['arm']=='fitted-c');zero=next(r for r in rows if r['option']==option and r['arm']=='zero-c')
                output['nested_gaps'].append({'case':case,'family':family,'option':option,'gap':max(0.,free['selection_score']-zero['selection_score'])})
    (HERE/'audit.json').write_text(json.dumps(output,indent=2));print(json.dumps(output,indent=2))

if __name__=='__main__':main()
