"""Independent frozen-input, causality and paired-gate checks; no GPS needed."""
import hashlib
import json
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parent


def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    assert read(OUT/'execution.json')['all_terminal'], 'cohort not complete'
    sample=read(OUT/'sample.json');rows=[]
    for m in sample['selected']:
        case=m['dataset_label'];folder=OUT/case
        row=dict(case=case,mode=m['mode'],file_hashes=0,historical_versions=0)
        inp=read(folder/'input_receipt.json') if (folder/'input_receipt.json').exists() else {}
        if inp:
            assert inp['sample_sha256']==sha(OUT/'sample.json')
            assert inp['recording_id']==m['recording_id']
            assert inp['raw_authority_digest']==m['raw_authority_digest']
            assert inp['GPS_or_localization_result_used'] is False
        prep=read(folder/'preparation_receipt.json') if (folder/'preparation_receipt.json').exists() else {}
        for name,h in prep.get('files_sha256',{}).items():
            assert sha(OUT/name)==h,(case,name)
            row['file_hashes']+=1
        if prep.get('status')=='prepared':
            receipt=read(folder/'receipt.json');cutoff=receipt['cutoff_utc_ns']
            assert cutoff<=receipt['origin_utc_ns']
            assert receipt['reference_position_used'] is False
            assert receipt['search_center']==[37.906,-122.545] and receipt['search_box_width_km']==25
            assert receipt['latest_max_epoch_utc_ns']<=cutoff
            assert receipt['latest_max_collection_utc_ns']<=cutoff
            for location in [folder,OUT/'causal_prior'/case]:
                previous=read(location/'previous_receipt.json')
                for r in previous['sources'].values():
                    assert r['epoch_utc_ns']<=cutoff and r['collected_utc_ns']<=cutoff
            history=read(OUT/'causal_phase_history'/(case+'.json'))
            for versions in history['past_versions'].values():
                for r in versions:
                    assert r['epoch']<=cutoff and r['collected_utc_ns']<=cutoff
                    row['historical_versions']+=1
            forecast=read(OUT/'causal_phase_history'/(case+'_forecast.json'))
            assert forecast['strictly_pre_RF'] and forecast['GPS_or_radio_used'] is False
            assert forecast['history_sha256']==sha(OUT/'causal_phase_history'/(case+'.json'))
            assert all(r['validation_time_ns']<=cutoff for r in forecast['transitions'])
        for method,path in [('algo02',folder/'algo02_result.json'),
                            ('baseline',OUT/'family_cavity/position'/(case+'.json'))]:
            if not path.exists():continue
            saved=read(path)
            if saved.get('status') not in ('accepted','complete'):continue
            pair=saved['policy_arms']
            assert set(pair)=={'c0','fitted_c'}
            for arm,fit in pair.items():
                gates=fit['gates']['tracks']+fit.get('linear_gates',[])
                assert gates and all(g['compatible'] for g in gates),(case,method,arm)
                xy=np.asarray(fit['endpoint_east_north_km'])
                assert np.isfinite(xy).all() and np.all(abs(xy)<=12.5+1e-8)
                if fit.get('linear_gates'):assert fit['final_phase_change_s']<=.01
            for name in ('active_points','predictive_points'):
                if name in pair['c0']:assert pair['c0'][name]==pair['fitted_c'][name],(case,name)
            row[method+'_paired_gates_verified']=True
        rows.append(row)
    result=dict(passed=True,rows=rows,checked_members=len(rows),
                checked_file_hashes=sum(r['file_hashes'] for r in rows),
                checked_historical_versions=sum(r['historical_versions'] for r in rows))
    (OUT/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}))


if __name__=='__main__':main()
