"""Two selected DS5 scans only: zero timing, fixed IDs, training-only polynomials."""
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_ds5_constant import (ScannerTrackingInputStore,TleArchiveReader,
    prepare_adaptive_tle_position_inputs,build_prediction_banks,
    RegionalTrackPredictionEvaluator,point_factory)
from polynomial_core import fit_residual

HERE=Path(__file__).resolve().parent
TARGETS={'scan-fw-3228d496423f0b3d':'08:10', 'scan-fw-fadea8b51ac3a4f7':'10:30'}


def main():
    source=HERE.parent/'2026_09_26_ds5_probabilistic/results.json'
    inventory_path=HERE.parent/'2026_09_26_ds5_probabilistic/input_audit.json'
    prior_path=HERE/'ds5_constant_results.json'
    old=json.loads(source.read_text())
    inventory={r['session_id']:r for r in json.loads(inventory_path.read_text())['captures']}
    previous={s['session_id']:s for s in json.loads(prior_path.read_text())['scans']}
    scans=[]
    for saved in old['scans']:
        sid=saved['session_id']
        if sid not in TARGETS:continue
        store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
        try:p=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
        finally:store.close()
        assert p.evidence_sha256==saved['evidence_sha256'] and p.snapshot_digest==saved['snapshot_digest']
        lookup={str(cid):i for i,cid in enumerate(p.catalogue.satellite_numbers)}
        expected={(r['site'],r['track_id']):r['evaluation_rms_hz'] for r in previous[sid]['rows'] if r['mode']=='zero'}
        rows=[];parity=0.;grid=np.array([0.])
        for track in p.tracks:
            for site,loc in saved['sites'].items():
                cid=saved['fixed_identities'][site][track.track_id]['candidate_id']
                banks,_=build_prediction_banks(p.catalogue,[lookup[cid]],p.start_utc_ns,[track],taus_s=grid)
                blocks=list(RegionalTrackPredictionEvaluator(banks,point_factory(loc['latitude_deg'],loc['longitude_deg']),taus_s=grid)(0,0))
                assert len(blocks)==1
                b=blocks[0];assert str(b.candidate_ids[0])==cid and b.visible[0]
                residual=b.measured_hz-b.predictions_hz[0,0]
                fits={'0':fit_residual(track.times_s,residual,b.training_mask,0)}
                fits['2']=fit_residual(track.times_s,residual,b.training_mask,2) if np.sum(b.training_mask)>3 else None
                parity=max(parity,abs(fits['0']['evaluation_rms_hz']-expected[site,track.track_id]))
                rows.append({'site':site,'track_id':track.track_id,'satellite_id':cid,'tau_s':0.,
                    'weight_s':len(np.unique(np.floor(track.times_s))),
                    'training_count':int(np.sum(b.training_mask)), 'fits':fits})
        assert len(rows)==len(p.tracks)*3 and parity<1e-6
        summary={}
        for site in saved['sites']:
            rr=[r for r in rows if r['site']==site and r['fits']['2'] is not None]
            arrays={d:np.array([r['fits'][d]['evaluation_rms_hz'] for r in rr]) for d in ('0','2')}
            summary[site]={d:{'median_hz':float(np.median(v)),'p90_hz':float(np.quantile(v,.9)),
                'weighted_rms_hz':float(np.sqrt(np.average(v*v,weights=[r['weight_s'] for r in rr])))} for d,v in arrays.items()}
            summary[site]['improved_tracks']=int(np.sum(arrays['2']<arrays['0']))
            summary[site]['eligible_tracks']=len(rr)
        scans.append({'session_id':sid,'utc':TARGETS[sid],'tracks':len(p.tracks),
            'location_errors_m':inventory[sid]['original_location_errors_m'],
            'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,
            'constant_parity_max_hz':parity,'summary':summary,'rows':rows})
        print(TARGETS[sid],json.dumps(summary),flush=True)
    assert len(scans)==2
    result={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'core_sha256':hashlib.sha256((HERE/'polynomial_core.py').read_bytes()).hexdigest(),
        'protocol':'Exactly zero time correction everywhere. Each site retains its own earlier training-only zero-timing IDs. '
            'OLS degree0 or degree2 (intercept+linear+quadratic) fitted on original training observations. '
            'Uncapped RMS on original evaluation observations; equal track weight in ECDF. '
            'Tracks with <=3 training observations retain constant RMS but no quadratic; both ECDFs use matched eligible tracks. '
            'No reassignment or retiming. '
            'Previously selected locations and reused masks: retrospective, not independent validation.', 'scans':scans}
    (HERE/'two_zero_results.json').write_text(json.dumps(result,indent=2)+'\n')
    colors={'reference':'#258348','sacramento':'#2369ad','reno':'#ce6525'}
    labels={'reference':'Known location','sacramento':'Sacramento estimate','reno':'Reno estimate'}
    fig,axes=plt.subplots(1,2,figsize=(13,5.5),sharex=True,sharey=True,layout='constrained')
    values=[]
    for ax,scan in zip(axes,scans):
        for site in colors:
            for d,style,term in [('0','-','constant'),('2','--','quadratic')]:
                x=np.sort([r['fits'][d]['evaluation_rms_hz'] for r in scan['rows'] if r['site']==site and r['fits']['2'] is not None])
                values.extend(x)
                ax.step(np.r_[x[0],x],np.r_[0,np.arange(1,len(x)+1)/len(x)*100],where='post',
                    color=colors[site],ls=style,lw=1.8,label=f'{labels[site]} — {term}')
        ax.set(title=f"{scan['utc']} UTC • {scan['summary']['reno']['eligible_tracks']}/{scan['tracks']} eligible tracks\nReno location error {scan['location_errors_m']['reno']/1000:.1f} km",
            xlabel='Evaluation residual RMS (Hz, log scale)',xscale='log',ylim=(0,102))
        ax.grid(alpha=.2)
    axes[0].set_ylabel('Tracks at or below RMS (%)')
    axes[0].set_xlim(min(values)*.8,max(values)*1.2)
    axes[0].legend(fontsize=8,loc='upper left')
    fig.suptitle('Zero timing correction • constant versus quadratic residual fits\nCoefficients fitted on training data; RMS on original evaluation observations')
    fig.savefig(HERE/'two_zero_distributions.png',dpi=180)
    plt.close(fig)


if __name__=='__main__':main()
