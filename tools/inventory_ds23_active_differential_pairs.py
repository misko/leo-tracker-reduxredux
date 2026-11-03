"""Find saved two-signal IQ probes backed by two active curved hypotheses.

Polynomial overlap is an ownership proposal, not independent satellite truth.
No RF covariance, catalogue assignment or position is changed by this audit.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np

from ds23_frequency_events import make_event_problem
from probe_ds23_sign_carrier_position import context_signed
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.retained_track_likelihood import PERIOD

SOURCE=ROOT/'reports/2026_10_21_ds23_common_probe_frequency'
OUT=ROOT/'reports/2026_10_22_ds23_differential_information'


def matching_curve(track,time_s,frequency_hz):
    matches=[]
    for piece in track['pieces']:
        if not piece['start_s']<=time_s<=piece['end_s']:continue
        z=(time_s-piece['reference_time_s'])/piece['time_scale_s']
        predicted=float(np.polynomial.polynomial.polyval(z,piece['coefficients_hz']))
        delta=float((predicted-frequency_hz+PERIOD/2)%PERIOD-PERIOD/2)
        limit=min(450.,max(150.,3*track['residual_rms_hz']))
        if abs(delta)<=limit:matches.append(dict(polynomial_value_hz=predicted,error_hz=delta,limit_hz=limit))
    return min(matches,key=lambda r:abs(r['error_hz'])) if matches else None


def one(case):
    scan,node,mask,powers,means,hyper,entries,signed,source=context_signed(case)
    p=make_event_problem(scan,node,mask,'c0',np.array(signed['policy_arms']['c0']['phase_reference']),powers,means,hyper,[])
    active={scan.tracks[i]['key']:(k,r,i) for k,(r,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)) if np.any(mask[sl])}
    protocol=read(SOURCE/'protocol.json');rows=read(SOURCE/'evaluation.json')['rows'];result=[]
    for row in rows:
        if row['case']!=case or row['status']!='complete':continue
        j=next(v['item']['job'] for v in protocol['jobs'] if v['item']['job']['case']==case and v['item']['job']['probe']==row['probe'])
        rx,ch,rf=j['lane'];tt=j['time_s'];frequencies=row['full']['uniform_support_mean_CFO_hz'];choices=[]
        for f in frequencies:
            matches=[]
            for track in scan.tracks:
                if (track['key'] not in active or (track['receiver'],track['channel'])!=(rx,ch)
                        or abs(track['rf_hz']-rf)>10):continue
                match=matching_curve(track,tt,f)
                if match:
                    k,r,i=active[track['key']]
                    matches.append(dict(match,component=track['key'],row_index=k,track_index=i,
                        candidate_index=r['candidate_index'],norad=r['candidate_norad']))
            choices.append(matches)
        unique=bool(all(len(m)==1 for m in choices) and choices[0][0]['norad']!=choices[1][0]['norad'])
        result.append(dict(case=case,probe=row['probe'],group=row['group'],stratum=row['stratum'],
            RF_common_model_qualified=row['RF_qualified'],choices=choices,unique_distinct_curved_pair=unique,
            joint_RF_difference_hz=row['full']['component_CFO_difference_hz'],
            conditional_difference_sigma_hz=row['full']['difference_sigma_proxy_hz'],job=j,
            no_new_measurement_or_satellite_identity_adopted=True))
    return result


def main():
    OUT.mkdir(exist_ok=True);source=read(SOURCE/'evaluation.json')
    cases=sorted({r['case'] for r in source['rows']})
    protocol=dict(cases=cases,source_protocol_sha256=sha(SOURCE/'protocol.json'),
        source_evaluation_sha256=sha(SOURCE/'evaluation.json'),all69original_probes_including_negative_controls=True,
        active_curved_only=True,no_time_extrapolation=True,RF_frequency_tolerance_hz=10,
        CFO_match_limit='min450,max150,3*polynomial_RMS',
        two_unique_distinct_family_proposals_required=True,no_GPS_future_TLE_or_new_RF=True,
        source_sha256=sha(Path(__file__)))
    path=OUT/'inventory_protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('differential RF inventory protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=8) as pool:
        rows=[r for f in as_completed([pool.submit(one,c) for c in cases]) for r in f.result()]
    result=dict(rows=rows,all_terminal=True,probes=len(rows),cases=len(cases),
        unique_pairs=sum(r['unique_distinct_curved_pair'] for r in rows),
        RF_qualified_unique_pairs=sum(r['unique_distinct_curved_pair'] and r['RF_common_model_qualified'] for r in rows),
        ownership_proposals_not_verified_satellite_labels=True,no_real_position_change=True)
    write(OUT/'inventory.json',result)
    print({k:v for k,v in result.items() if k!='rows'},flush=True)
    for r in rows:
        if r['unique_distinct_curved_pair']:print(r['case'],r['probe'],r['RF_common_model_qualified'],[m[0]['norad'] for m in r['choices']],flush=True)


if __name__=='__main__':main()
