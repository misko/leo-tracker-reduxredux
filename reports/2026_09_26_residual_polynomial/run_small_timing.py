"""Two fixed DS5 scans only; constant correction and +/-1s satellite timing."""
import json
import hashlib
from pathlib import Path
import numpy as np
from run_ds5_constant import (ScannerTrackingInputStore,TleArchiveReader,
    prepare_adaptive_tle_position_inputs,build_prediction_banks,
    RegionalTrackPredictionEvaluator,point_factory)
from small_timing_core import profile,choose_shared,aggregate

HERE=Path(__file__).resolve().parent
TARGETS={'scan-fw-3228d496423f0b3d':'08:10','scan-fw-fadea8b51ac3a4f7':'10:30'}


def main():
    source=HERE.parent/'2026_09_26_ds5_probabilistic/results.json'
    old=json.loads(source.read_text())
    preceding=json.loads((HERE/'two_zero_results.json').read_text())
    scans=[];grid=np.arange(-10,11)/10
    for saved in old['scans']:
        sid=saved['session_id']
        if sid not in TARGETS:continue
        prev=next(s for s in preceding['scans'] if s['session_id']==sid)
        expected={(r['site'],r['track_id']):r for r in prev['rows']}
        store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
        try:p=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
        finally:store.close()
        assert p.evidence_sha256==saved['evidence_sha256'] and p.snapshot_digest==saved['snapshot_digest']
        lookup={str(cid):i for i,cid in enumerate(p.catalogue.satellite_numbers)}
        profiles={site:[] for site in saved['sites']};parity=0.
        for track in p.tracks:
            for site,loc in saved['sites'].items():
                cid=saved['fixed_identities'][site][track.track_id]['candidate_id']
                banks,_=build_prediction_banks(p.catalogue,[lookup[cid]],p.start_utc_ns,[track],taus_s=grid)
                blocks=list(RegionalTrackPredictionEvaluator(banks,point_factory(loc['latitude_deg'],loc['longitude_deg']),taus_s=grid)(0,0))
                assert len(blocks)==1
                b=blocks[0];assert str(b.candidate_ids[0])==cid and b.visible[0]
                fit=profile(b.measured_hz,b.predictions_hz[0],b.training_mask)
                e=expected[site,track.track_id]
                parity=max(parity,abs(np.sqrt(fit['eval_mse'][10])-e['fits']['0']['evaluation_rms_hz']))
                profiles[site].append(dict(track_id=track.track_id,satellite_id=cid,observations=len(track.times_s),
                    plot_eligible=e['fits']['2'] is not None,**fit))
        assert parity<1e-6
        sites={}
        for site,rr in profiles.items():
            chosen=choose_shared(rr,grid);rows=[]
            for r in rr:
                j=chosen[r['satellite_id']]
                rows.append({k:r[k] for k in ('track_id','satellite_id','observations','plot_eligible')}|
                    {'tau_s':float(grid[j]),'zero_mse':float(r['eval_mse'][10]),'corrected_mse':float(r['eval_mse'][j]),
                     'zero_offset_hz':float(r['offset'][10]),'corrected_offset_hz':float(r['offset'][j])})
            assert len(rows)==len(p.tracks)
            sites[site]={'all_tracks':{k:aggregate(rows,k) for k in ('zero_mse','corrected_mse')},
                'previous_plot_tracks':{k:aggregate([r for r in rows if r['plot_eligible']],k) for k in ('zero_mse','corrected_mse')},
                'satellite_count':len(chosen),'boundary_satellites':sum(j in (0,20) for j in chosen.values()),
                'timing_by_satellite':{cid:float(grid[j]) for cid,j in chosen.items()},'rows':rows}
        scans.append({'session_id':sid,'utc':TARGETS[sid],'tracks':len(p.tracks),
            'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,'zero_parity_max_hz':parity,'sites':sites})
        print(TARGETS[sid],json.dumps({s:{k:v for k,v in d.items() if k not in ('rows','timing_by_satellite')} for s,d in sites.items()}),flush=True)
    assert len(scans)==2
    output={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'core_sha256':hashlib.sha256((HERE/'small_timing_core.py').read_bytes()).hexdigest(),
        'protocol':'Fixed branch-specific training-zero IDs and fixed locations. Per-track OLS constant profiled at each tau. '
            'One tau per satellite per scan per site, minimizing sum training SSE across all assigned tracks, '
            'uniform grid -1..+1s step0.1; ties prefer smallest abs(tau). No drift or reassignment. '
            'Evaluation RMS uncapped. Equal-track aggregation sqrt(mean(track MSE)); '
            'size weights total observations (training+evaluation), same fits for both aggregates. '
            'All39/51 tracks primary; prior plot subset sensitivity uses same all-track-fitted timings. '
            'Retrospective reused masks and selected sites, not fresh validation or localization.', 'scans':scans}
    (HERE/'small_timing_results.json').write_text(json.dumps(output,indent=2)+'\n')


if __name__=='__main__':main()
