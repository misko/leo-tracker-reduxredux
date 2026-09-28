"""Explicit OLS constant-only RMS across DS5, at fixed independent sites."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from polynomial_core import fit_residual

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_26_reno_track_audit'))
from compare_scan_clock import (ScannerTrackingInputStore,TleArchiveReader,
    prepare_adaptive_tle_position_inputs,build_prediction_banks,
    RegionalTrackPredictionEvaluator,point_factory)


def main():
    source=HERE.parent/'2026_09_26_ds5_probabilistic/results.json'
    old=json.loads(source.read_text()); scans=[]
    for previous in old['scans']:
        sid=previous['session_id'];store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
        try:p=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
        finally:store.close()
        assert p.evidence_sha256==previous['evidence_sha256'] and p.snapshot_digest==previous['snapshot_digest']
        lookup={str(cid):i for i,cid in enumerate(p.catalogue.satellite_numbers)}
        free=next(e for e in previous['experiments'] if e['mode']=='free_per_track' and e['noise_scale_hz']==100)['sites']
        timings={s:{r['track_id']:r for r in free[s]['tracks']} for s in free}
        rows=[];parity=0.
        for t in p.tracks:
            for site,loc in previous['sites'].items():
                original=previous['fixed_identities'][site][t.track_id];cid=original['candidate_id']
                saved=timings[site][t.track_id];assert saved['satellite_id']==cid
                tau=saved['timing']['map_s'];grid=np.array(sorted({0.,tau}))
                banks,_=build_prediction_banks(p.catalogue,[lookup[cid]],p.start_utc_ns,[t],taus_s=grid)
                blocks=list(RegionalTrackPredictionEvaluator(banks,point_factory(loc['latitude_deg'],loc['longitude_deg']),taus_s=grid)(0,0))
                assert len(blocks)==1
                b=blocks[0];assert str(b.candidate_ids[0])==cid
                for mode,value in [('zero',0.),('fixed_training_timing',tau)]:
                    j=int(np.flatnonzero(grid==value)[0])
                    f=fit_residual(t.times_s,b.measured_hz-b.predictions_hz[0,j],b.training_mask,0)
                    if mode=='zero':parity=max(parity,abs(f['training_rms_hz']-original['training_rms_hz']))
                    rows.append({'site':site,'mode':mode,'track_id':t.track_id,'satellite_id':cid,
                        'tau_s':value,'weight_s':len(np.unique(np.floor(t.times_s))),
                        'evaluation_rms_hz':f['evaluation_rms_hz'],'training_rms_hz':f['training_rms_hz']})
        assert parity<1e-6
        assert len(rows)==len(p.tracks)*6
        scores={}
        for mode in ('zero','fixed_training_timing'):
            scores[mode]={}
            for site in previous['sites']:
                rr=[r for r in rows if r['mode']==mode and r['site']==site]
                weights=np.array([r['weight_s'] for r in rr]);rms=np.array([r['evaluation_rms_hz'] for r in rr])
                scores[mode][site]={'rms_hz':float(np.sqrt(np.average(rms**2,weights=weights))),
                    'capped800_rms_hz':float(np.sqrt(np.average(np.minimum(rms,800)**2,weights=weights)))}
        scans.append({'session_id':sid,'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,
            'scores':scores,'rows':rows,'zero_training_parity_max_hz':parity})
        out={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'protocol':'Training-only zero-timing satellite IDs from old DS5 frozen independently per site. '
                'OLS constant fit training-only; original evaluation RMS. Zero time or previous flat per-track '
                'robust100Hz training-MAP time frozen (not OLS-optimized time). Occupied-second weighted location RMS. '
                'Uncapped main, 800Hz track cap sensitivity. No drift, new selection, location search or cross-site proposals. '
                'Reused masks and selected locations: retrospective, not fresh validation.', 'scans':scans}
        (HERE/'ds5_constant_results.json').write_text(json.dumps(out,indent=2)+'\n')
        print('DONE',len(scans),sid,flush=True)


if __name__=='__main__':main()
