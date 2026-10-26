"""Archived target compatibility after forecasting; no raw samples or scoring."""
import csv
import json
from collections import Counter
from pathlib import Path
import numpy as np
import predictor as p
import study

HERE=Path(__file__).resolve().parent
TIMING=[2,16,64,256]
CFO=[100,500,3000]


def main():
    study.bound(); predictions=study.read(HERE/'predictions.json')
    targets={r['prediction_id']:r for r in study.read(HERE/'evaluation_targets.json')['rows']}
    cells=[]; modes=[]; redactions=0
    for row in predictions['rows']:
        h=row['header'];f=row.get('forecast');period=h['sample_rate_hz']/750
        original=targets[h['prediction_id']]['target_original']
        target=p.measured_candidates(original,h) if original else []
        evaluated=[]
        for order,m in enumerate(f['modes'] if f else []):
            full=m['full']
            errors=[dict(target_original_rank=t['candidate_rank'],
                timing_delta_samples=p.wrap(t['epoch_samples']-full['epoch_samples'],period),
                CFO_delta_hz=t['CFO_hz']-full['CFO_hz']) for t in target]
            item=dict(prediction_id=h['prediction_id'],case=h['case'],channel=h['channel'],receiver_id=h['receiver_id'],
                mode_order=order+1,mode_status=m['status'],donor_count=m['donor_count'],
                elapsed_s=full['elapsed_s'],missed_visits_after_latest=m['missed_visits_after_latest'],
                missed_visits_between_donors=m['missed_visits_between_donors'],
                timing_half_width_samples=full['timing_half_width_samples'],CFO_half_width_hz=full['CFO_half_width_hz'],
                timing_rate_samples_per_s=full['timing_rate_samples_per_s'],CFO_rate_hz_per_s=full['CFO_rate_hz_per_s'],
                target_original_candidates=len(target),errors_to_all_original_target_modes=errors)
            for tw in TIMING:
                for cw in CFO:item[f'joint_T{tw}_F{cw}']=any(abs(e['timing_delta_samples'])<=tw and abs(e['CFO_delta_hz'])<=cw for e in errors)
            item['joint_heuristic_band']=any(abs(e['timing_delta_samples'])<=full['timing_half_width_samples'] and
                abs(e['CFO_delta_hz'])<=full['CFO_half_width_hz'] for e in errors)
            item['CFO_only_3000']=any(abs(e['CFO_delta_hz'])<=3000 for e in errors)
            item['timing_only_64']=any(abs(e['timing_delta_samples'])<=64 for e in errors)
            evaluated.append(item);modes.append(item)
        primary=evaluated[:1]
        cell=dict(**h,status=row['status'],target_original_gatepass=bool(target),target_original_modes=len(target),
            forecast_available=bool(evaluated),retained_modes=len(evaluated),
            primary_donor_count=primary[0]['donor_count'] if primary else 0,
            primary_elapsed_s=primary[0]['elapsed_s'] if primary else None,
            primary_timing_half_width_samples=primary[0]['timing_half_width_samples'] if primary else None,
            primary_CFO_half_width_hz=primary[0]['CFO_half_width_hz'] if primary else None,
            any_one_donor=any(m['mode_status']=='one_donor_fallback' for m in evaluated),
            any_multi_donor=any(m['donor_count']>=2 for m in evaluated),
            any_missed_visit=any(m['missed_visits_after_latest']+m['missed_visits_between_donors']>0 for m in evaluated),
            latest_visit_gatepassing=f['latest_visit_gatepassing'] if f else False,
            history_visits=f['history_visits'] if f else 0,
            visits_with_gatepassing_candidates=f['visits_with_gatepassing_candidates'] if f else 0,
            ambiguous_extensions=f['ambiguous_extensions'] if f else 0,modes_pruned=f['modes_pruned'] if f else 0)
        for tw in TIMING:
            for cw in CFO:
                key=f'joint_T{tw}_F{cw}'
                for count in [1,2,4,8]:cell[f'top{count}_{key}']=any(m[key] for m in evaluated[:count])
        cell['any_joint_heuristic_band']=any(m['joint_heuristic_band'] for m in evaluated)
        cell['primary_joint_heuristic_band']=any(m['joint_heuristic_band'] for m in primary)
        cell['any_CFO_only_3000']=any(m['CFO_only_3000'] for m in evaluated)
        cell['any_timing_only_64']=any(m['timing_only_64'] for m in evaluated)
        cells.append(cell)
    def counts(rows):
        names=['target_original_gatepass','forecast_available','any_one_donor','any_multi_donor','any_missed_visit',
               'latest_visit_gatepassing','any_joint_heuristic_band','primary_joint_heuristic_band','any_CFO_only_3000','any_timing_only_64']
        names += [f'top{k}_joint_T{tw}_F{cw}' for k in [1,2,4,8] for tw in TIMING for cw in CFO]
        return dict(cells=len(rows),**{key:sum(bool(r[key]) for r in rows) for key in names},
            target_gatepass_and_forecast=sum(r['target_original_gatepass']and r['forecast_available']for r in rows),
            modes=sum(r['retained_modes']for r in rows),ambiguous_extensions=sum(r['ambiguous_extensions']for r in rows),
            pruned_modes=sum(r['modes_pruned']for r in rows))
    gap_ranges=[(0,.5),(.5,1),(1,2),(2,4.51)]
    summary=dict(schema='sparse-prediction-archived-survey/v1',protocol_sha256=study.sha(HERE/'protocol.json'),
        predictions_sha256=study.sha(HERE/'predictions.json'),evaluation_targets_sha256=study.sha(HERE/'evaluation_targets.json'),
        overall=counts(cells),by_channel={str(ch):counts([r for r in cells if r['channel']==ch])for ch in study.CHANNELS},
        by_channel_receiver={f'CH{ch}-RX{rx}':counts([r for r in cells if r['channel']==ch and r['receiver_id']==rx])
            for ch in study.CHANNELS for rx in [0,1]},
        by_primary_gap_s={f'{lo}..{hi}':counts([r for r in cells if r['primary_elapsed_s']is not None and lo<=r['primary_elapsed_s']<hi])
            for lo,hi in gap_ranges},
        by_primary_donor_count={label:counts([r for r in cells if low<=r['primary_donor_count']<=high])
            for label,low,high in [('none',0,0),('one',1,1),('two',2,2),('three_plus',3,12)]},
        compatibility_is_target_chosen_best_case_not_predictor_selection=True,
        archived_original_fullwindow_acquisition_exposed=True,external_signal_truth=False,
        validation_outcomes_opened=False,raw_IQ_reads=0,new_independent_measurements=0)
    study.write(HERE/'summary.json',summary)
    study.write(HERE/'mode_evaluation.json',dict(rows=modes,target_selection_is_evaluation_only=True))
    for name,rows in [('cells.csv',cells),('mode_evaluation.csv',[{k:v for k,v in m.items()if k!='errors_to_all_original_target_modes'}for m in modes])]:
        with(HERE/name).open('x')as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps(summary['overall'],indent=2))


if __name__=='__main__':main()
