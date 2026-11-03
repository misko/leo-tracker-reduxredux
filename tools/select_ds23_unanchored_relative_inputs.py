"""Freeze long relative-CFO curves without requiring original graph anchors.

These are existing RF-qualified measurements and catalogue hypotheses, not
verified identities or an accepted position method. No IQ is reread.
"""

from pathlib import Path
import numpy as np

from run_algo01_ds23_sample import ROOT,read,write,sha

PARENT=ROOT/'reports/2026_10_22_ds23_exact_differential_phase'
OUT=PARENT/'unanchored_relative_inputs'


def main():
    OUT.mkdir(exist_ok=True);source=read(PARENT/'refined/execution.json');assert source['all_terminal']
    protocol=dict(source_sha256=sha(PARENT/'refined/execution.json'),
        selection='regional-centre exact nomination; local saved-pool gap>=2log20; relative residual noise screen passes',
        current_RF_mode_and_GPS_not_used=True,no_original_active_graph_anchor_required=True,
        minimum_groups_for_position=2,minimum_distinct_nominated_satellites=3,
        local_gap_is_not_global_identity_confidence=True,RF_noise_is_empirical_polynomial_residual_not_absolute_error_coverage=True,
        original_RF_quality_and_native_relative_curvature_checks_retained=True,
        source_sha256_tool=sha(Path(__file__)))
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('relative-input protocol changed')
    if not path.exists():write(path,protocol)
    results=[]
    for case in sorted({g['case'] for g in source['rows']}):
        groups=[]
        for item in source['rows']:
            if item['case']!=case or item['status']!='complete':continue
            candidates=item['results']['regional_centre']['candidates']
            if len(candidates)<2 or candidates[1]['score']-candidates[0]['score']<2*np.log(20):continue
            best=candidates[0]
            if not best['relative_residual_noise']['noise_screen_pass']:continue
            root=Path(item['source']);evaluation=read(root/'evaluation.json');rfprotocol=read(root/'protocol.json')
            jobs={r['probe']:r for r in rfprotocol['jobs'] if r['group']==item['group']}
            rf=sorted([r for r in evaluation['rows'] if r['case']==case and r['probe'] in jobs and r['status']=='complete' and r['two_components_qualified']],key=lambda r:r['time_s'])
            selected=next(r for r in rfprotocol['selected'] if r['group']==item['group'])
            assert all(selected['pair']['geometry_checks'].values())
            rows=[dict(probe=r['probe'],time_s=r['time_s'],first_value_hz=r['refined_first_value'],
                second_value_hz=r['refined_second_value'],original_probe_observation_id=jobs[r['probe']]['first']['probe_observation_id']) for r in rf]
            assert len({r['probe'] for r in rows})==len(rows)
            groups.append(dict(group=item['group'],lane=item['lane'],points=rows,
                span_s=float(rows[-1]['time_s']-rows[0]['time_s']),noise_sigma_hz=item['noise_sigma_hz'],
                nomination=best,alternative_nominations=candidates[1:3],
                native_geometry_checks=selected['pair']['geometry_checks'],
                source_RF_sha256=sha(root/'evaluation.json'),source_RF_protocol_sha256=sha(root/'protocol.json'),
                source_refinement_sha256=sha(PARENT/'refined'/(item['group']+'.json'))))
        labels=sorted({r[role+'_index'] for g in groups for r in [g['nomination']] for role in ['first','second']})
        eligible=len(groups)>=2 and len(labels)>=3
        result=dict(case=case,groups=groups,nominated_candidate_indices=labels,eligible=eligible,
            not_a_verified_satellite_identity_or_position_result=True)
        write(OUT/(case+'.json'),result);results.append(dict(case=case,groups=len(groups),labels=len(labels),eligible=eligible,
            relative_observations=sum(len(g['points']) for g in groups),source_sha256=sha(OUT/(case+'.json'))))
    write(OUT/'evaluation.json',dict(rows=results,eligible_cases=sum(r['eligible'] for r in results),
        no_new_IQ_GPS_future_TLE_or_position_fit=True,all_terminal=True))
    print(results,flush=True)


if __name__=='__main__':main()
