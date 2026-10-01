"""Distinguish coverage losses from reference-source purity failures."""
import json
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
BASE=REPORTS/'2026_09_30_arm_fast_tracks/server-baseline/output'
sys.path.insert(0,str(REPORTS/'2026_09_30_arm_curvature_tracks/evaluation'))
import compare_membership as m

def main():
    so=m.read_observations(BASE/'server-observations.tsv');ss=m.read_sources(BASE/'server-candidate-map.tsv',so)
    refs=m.read_tracks(BASE/'server-tracks.tsv',so).values
    settings=json.loads((REPORTS/'2026_09_30_arm_curvature_tracks/evaluation/thresholds.json').read_text())
    evaluation=json.loads((HERE/'analysis/evaluation.json').read_text())
    indexes=sorted(set([2,8,30,34,47]+evaluation['reviewed']['lost']))
    result={i:{'reference':i,'input_support':next(r for r in evaluation['reference_input_support'] if r['reference_track_index']==i)} for i in indexes}
    for label,op,mp,tp in [('original',BASE/'arm-observations.tsv',BASE/'arm-candidate-map.tsv',REPORTS/'2026_09_30_arm_streaming_tracks/qualification/rolling-backfill/arm-0.tsv'),
        ('ungated',HERE/'analysis/observations.tsv',HERE/'analysis/candidate-map.tsv',HERE/'analysis/tracks-0.tsv')]:
        obs=m.read_observations(op);sources=m.read_sources(mp,obs);bank=m.read_tracks(tp,obs).values
        for i in indexes:
            ref=refs[i]
            choices=[(m.membership_metrics(ref,t,so,obs,ss,sources,settings),t) for t in bank if t.lane==ref.lane]
            metrics,track=max(choices,key=lambda pair:(m.complete(pair[0],settings),pair[0]['consistent_source_count'],pair[0]['in_span_output_purity']))
            origin=ref.start_ns;spacing=11.2e9/ref.lane.rf_hz/4.4e-6
            reference=sorted(((so[p.candidate].center_ns-origin)/1e9,p.dealiased_cfo_hz) for p in ref.points)
            t,f=np.array(reference).T
            shared=set(metrics['consistent_sources']);extras=[]
            if metrics['consistent_source_count']:
                for p in track.points:
                    o=obs[p.candidate];source=':'.join(map(str,sources[p.candidate]))
                    if source in shared or not ref.start_ns<=o.center_ns<=ref.end_ns:continue
                    when=(o.center_ns-origin)/1e9
                    if not t[0]<=when<=t[-1]:continue
                    residual=m.circular_distance(p.dealiased_cfo_hz-np.interp(when,t,f),spacing)
                    extras.append({'source':source,'time_from_ref_start_s':when,'interpolated_reference_residual_hz':residual})
            result[i][label]={'output_index':track.index,'complete':m.complete(metrics,settings),**metrics,
                'extras_within_reference_center_range':extras,
                'extra_residual_median_hz':float(np.median([x['interpolated_reference_residual_hz'] for x in extras])) if extras else None,
                'extra_residual_p95_hz':float(np.percentile([x['interpolated_reference_residual_hz'] for x in extras],95)) if extras else None}
    doc={'rows':list(result.values()),'extra_residual_definition':'Circular CFO difference from linear interpolation of server-assigned measured points, in reference center range; geometric diagnostic, not identity truth'}
    (HERE/'analysis/change-audit.json').write_text(json.dumps(doc,indent=2)+'\n')
    for i,r in result.items():
        n=r['ungated'];print(i,n['consistent_source_count'],n['reference_source_count'],round(n['in_span_output_purity'],3),
                            'extra residual median/p95',n['extra_residual_median_hz'],n['extra_residual_p95_hz'])

if __name__=='__main__':main()
