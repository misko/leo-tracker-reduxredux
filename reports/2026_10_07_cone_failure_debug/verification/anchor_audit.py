"""Read-only independent anchor receipt audit; no fitting."""
import hashlib,json
from dataclasses import replace
import numpy as np
import audit as a

def main():
    path=a.PARENT/'paired_background/anchor_results.json';receipt=json.loads(path.read_text())
    assert receipt['status']=='complete'
    assert receipt['protocol_sha256']==hashlib.sha256((path.parent/'anchor_probe.py').read_bytes()).hexdigest()
    output={'receipt_sha256':a.controls.digest_bytes(path.read_bytes()),'selected':[],'checks':[],'nested_gaps':[]}
    pairs_doc=json.loads((a.PARENT/'identity/paired_topone.json').read_text())
    for case in receipt['cases']:
        key=case['case'];doc,old,obs,prior,bank,cp,prefix=a.oracle.load(key)
        assert case['evidence_sha256']==doc['evidence_sha256']
        assert all(hashlib.sha256(a.Path(p).read_bytes()).hexdigest()==h for p,h in case['source_hashes'].items())
        pairs=np.array([[r['row0'],r['row1']] for r in pairs_doc['cases'][key]['100ns']['rows']])
        basin=case['basin'];assoc=cp.get(prefix+':'+basin+':association')['result'];cal=cp.get(prefix+':'+basin+':calibration')['result'];subset=bank.select(assoc['selected_indices'])
        score=replace(a.PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1.)
        for arm,init in case['initializers'].items():
            original=np.asarray(init['original_vector'])
            assert a.controls.vector_digest(original)==init['original_sha256']
            for anchor,row in init['anchors'].items():
                v=np.asarray(row['vector']);assert a.controls.vector_digest(v)==row['vector_sha256']
                assert np.array_equal(v[np.r_[0:2,6:len(v)]],original[np.r_[0:2,6:len(v)]])
                retained=[2,3] if anchor=='anchor-rx0' else [4,5]
                assert np.array_equal(v[retained],original[retained])
        assert len(case['runs'])==12
        for row in case['runs']:
            assert row['seed_sha256']==case['initializers'][row['arm']]['anchors'][row['origin']]['vector_sha256']
        for row in case['selections']:
            v=np.asarray(row['vector']);arm=row['arm'];model=row['model']
            assert row['selection_score']==min(r['selection_score'] for r in case['candidates'] if r['model']==model and r['arm']==arm)
            obj=a.background.BackgroundObjective(obs,subset,prior,score,receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']),pairs=pairs,rho=row['rho'],eta=row['eta'])
            value,g,_=obj.evaluate(v)
            audit=a.controls.audit(v,g,obj.basis,arm,prior.radius_km,np.asarray(case['center']),case['radius_km'],max(-20.,subset.nodes_s[0]-obs.times_s.min()),min(20.,subset.nodes_s[-1]-obs.times_s.max()))
            assert abs(value-row['objective'])<1e-6 and abs(audit['stationarity']-row['stationarity'])<1e-5
            assert audit['converged']==row['converged'] and audit['feasible']
            if arm=='zero-c':assert v[6]==0
            lat,lon=np.radians(a.coordinates(prior,v[:2]));ref_lat,ref_lon=np.radians([doc['reference_latitude_deg'],doc['reference_longitude_deg']])
            hav=np.sin((lat-ref_lat)/2)**2+np.cos(lat)*np.cos(ref_lat)*np.sin((lon-ref_lon)/2)**2
            error=float(2*6371008.8*np.arcsin(np.sqrt(np.clip(hav,0,1))))
            assert abs(error-row['horizontal_error_m'])<1e-5
            clock=a.clock(obs,obj,v,pairs)
            for k in ('median_absolute_residual_hz','p90_absolute_residual_hz','robust_residual_slope_hz_s'):assert abs(clock[k]-row['pair_clock'][k])<1e-6
            output['selected'].append({'case':key,'model':model,'arm':arm,'selection_score':row['selection_score'],'error_m':error,'origin':row['origin'],'independent_audit':audit,'clock':clock})
        for model in receipt['models']:
            rows=[r for r in case['selections'] if r['model']==model]
            free=next(r for r in rows if r['arm']=='fitted-c');zero=next(r for r in rows if r['arm']=='zero-c')
            output['nested_gaps'].append({'case':key,'model':model,'gap':max(0.,free['selection_score']-zero['selection_score'])})
        output['checks'].append(f'{key}: all 12 fits use matched own-arm anchors; physical state unchanged; score-only selection, source hashes, objective, independent KKT and clock metrics agree. Conditional on one retained basin.')
    (a.HERE/'anchor_audit.json').write_text(json.dumps(output,indent=2))

if __name__=='__main__':main()
