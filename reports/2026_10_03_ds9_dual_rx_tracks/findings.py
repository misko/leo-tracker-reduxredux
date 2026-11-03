"""Summarize completed DS9 case audit without changing memberships or fits."""
import hashlib
import json
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent


def main():
    receipt=json.loads((HERE/'receipt.json').read_text());rows=[]
    for summary in receipt['cases']:
        case=json.loads((HERE/'cases'/(summary['case_id']+'.json')).read_text())
        p=case['pairs'];times=np.sort([v['time_s'] for v in p]);models=case['summary']['channel_offset_controlled_models']
        cv=np.array([models[str(i)]['five_time_block_held_median_absolute_error_hz'] for i in range(3)])
        coverage=[models[str(i)]['held_count']/len(p) for i in range(3)]
        slope=models['1']['slope_hz_s_at_150s']
        population=HERE.parent/'2026_09_28_ds9_post_ds8'
        archived=json.loads((population/'analysis'/(case['session_id']+'.json')).read_text())['tracking']['product']
        pose=json.loads((population/'pose'/(case['session_id']+'.json')).read_text())['pose_authority']
        old=archived['observer_site'];lat1,lat2=np.deg2rad([old['latitude_deg'],pose['latitude_deg']])
        dlon=np.deg2rad(old['longitude_deg']-pose['longitude_deg'])
        separation=6371008.8*2*np.arcsin(np.sqrt(np.sin((lat1-lat2)/2)**2+np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2))
        item=dict(**summary,maximum_pair_gap_s=float(np.max(np.diff(times))),
            archived_observer_site=old,capture_bound_lat_lon=[pose['latitude_deg'],pose['longitude_deg']],
            approximate_horizontal_site_discrepancy_m=float(separation),
            paired_coverage_fraction=case['paired_span_s']/case['overlap_s'],held_coverage_fraction=coverage,
            strong_margin_pair_count=case['summary']['strong_margin_at_least_0p4_both']['pair_count'],
            linear_held_improvement_percent=float(100*(1-cv[1]/cv[0])),
            quadratic_vs_linear_held_improvement_percent=float(100*(1-cv[2]/cv[1])),
            line_predicted_change_across_paired_span_hz=float(slope*np.ptp(times)),
            largest_epoch_mismatch_ns=max(abs(v['epoch_difference_s'])*1e9 for v in p))
        assert item['pair_count']>=20 and case['paired_span_s']>=30
        assert item['largest_epoch_mismatch_ns']<=100
        assert len({(v['visit'],v['probe']) for v in p})==len(p)
        assert len({v['rf_hz'] for v in p})==1
        rows.append(item)
    assert len(rows)==16 and len({r['session_id'] for r in rows})==16
    helpers=[HERE/'audit.py',HERE/'findings.py',HERE.parent/'2026_10_02_ds13_timing_em/native_rx_difference.py',
             HERE.parent/'2026_10_02_cross_scan_drift_evidence/check_other_scans.py',
             HERE.parent/'2026_10_02_multiscan_localization/edge_alias_diagnostic.py',
             HERE.parent/'2026_10_02_localization_benchmark/export_ds11.py']
    result=dict(cases=rows,total_pairs=sum(r['pair_count'] for r in rows),
        linear_beats_constant_count=sum(r['linear_held_improvement_percent']>0 for r in rows),
        linear_improves_at_least20percent_count=sum(r['linear_held_improvement_percent']>=20 for r in rows),
        quadratic_beats_linear_count=sum(r['quadratic_vs_linear_held_improvement_percent']>0 for r in rows),
        quadratic_improves_at_least20percent_count=sum(r['quadratic_vs_linear_held_improvement_percent']>=20 for r in rows),
        code_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in helpers},
        interpretation='Improvement counts describe this retrospectively selected 16-scan cohort, not significance tests. '
        'Archived radio-null score is minimum held-out score over line/quadratic/cubic alternatives; '
        'this best-of-three control favors flexible curves and failing to beat it does not prove a wrong satellite. '
        'Archived candidate scores also use an observer position different from the capture-bound roof location; '
        'these scores are not a fresh identity test at the correct site. Differential analysis uses no location. '
        'Matched-pair slopes measure relative chain/estimator behavior only conditional on common emission. '
        'Unknown absolute drift, transmitter drift, and orbital identity remain unresolved.')
    (HERE/'findings.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
