"""Equal-scan RMS discrimination summaries, with explicit accounting."""
import json
from pathlib import Path
from statistics import mean,median

HERE=Path(__file__).resolve().parent
DEVELOPMENT={'scan-fw-d86e8f23c0624bac','scan-fw-dc1153010e57ac76'}


def summarize(scans, inventory):
    inputs={r['session_id']:r for r in inventory['captures']}
    ids=[s['session_id'] for s in scans]
    if len(ids)!=len(set(ids)):raise ValueError('duplicate scan')
    buckets={}
    for scan in scans:
        sid=scan['session_id'];inp=inputs[sid]
        if scan['evidence_sha256']!=inp['evidence_sha256']:raise ValueError('evidence mismatch')
        for site in ('sacramento','reno'):
            scopes=['all']
            if sid not in DEVELOPMENT:scopes.append('excluding_two_development')
            if inp['original_location_errors_m'][site]>=100000:scopes.append('error_ge100km')
            for mode,scores in scan['scores'].items():
                for metric in ('rms_hz','capped800_rms_hz'):
                    ref=scores['reference'][metric];value=scores[site][metric]
                    for scope in scopes:buckets.setdefault((scope,mode,metric,site),[]).append((ref,value))
    rows=[]
    for (scope,mode,metric,site),values in sorted(buckets.items()):
        gaps=[a-b for a,b in values]
        rows.append({'scope':scope,'mode':mode,'metric':metric,'site':site,'scans':len(values),
            'reference_wins':sum(g < -1e-8 for g in gaps), 'ties':sum(abs(g)<=1e-8 for g in gaps),
            'reference_mean_hz':mean(a for a,b in values),'estimate_mean_hz':mean(b for a,b in values),
            'mean_gap_hz':mean(gaps),'median_gap_hz':median(gaps)})
    return {'completed':len(ids),'missing':sorted(set(inputs)-set(ids)),'summaries':rows}


if __name__=='__main__':
    data=json.loads((HERE/'ds5_constant_results.json').read_text())
    inventory=json.loads((HERE.parent/'2026_09_26_ds5_probabilistic/input_audit.json').read_text())
    output=summarize(data['scans'],inventory)
    assert not output['missing']
    (HERE/'ds5_constant_summary.json').write_text(json.dumps(output,indent=2)+'\n')
    for row in output['summaries']:print(row)
