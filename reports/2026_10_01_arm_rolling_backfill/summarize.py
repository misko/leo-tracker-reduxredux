"""Compare the bounded backfill trial with the frozen forward-only baseline."""
import json
from pathlib import Path
from statistics import median
import sys

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'2026_09_30_arm_streaming_tracks'
BASE=HERE.parent/'2026_09_30_arm_fast_tracks/server-baseline/output'
sys.path.insert(0,str(HERE.parent/'2026_09_30_arm_curvature_tracks/evaluation'))
import compare_membership as m


def main():
    new=OLD/'qualification/rolling-backfill'
    so=m.read_observations(BASE/'server-observations.tsv')
    refs=m.read_tracks(BASE/'server-tracks.tsv',so).values
    buckets={'short':set(),'medium':set(),'long':set()}
    for ref in refs:
        if ref.index==10: continue
        seconds=(ref.end_ns-ref.start_ns)/1e9
        buckets['short' if seconds<15 else 'medium' if seconds<30 else 'long'].add(ref.index)
    rows=[]
    for side in ['arm','server']:
        old=json.loads((OLD/f'qualification/rolling/{side}-evaluation.json').read_text())
        trial=json.loads((new/f'{side}-evaluation.json').read_text())
        before=set(old['primary']['reference_segments_with_any_complete_output_indexes'])-{10}
        after=set(trial['primary']['reference_segments_with_any_complete_output_indexes'])-{10}
        row={'side':side,'gained':sorted(after-before),'lost':sorted(before-after),
             'before':len(before),'after':len(after),
             'hypotheses_before':old['output']['tracks'],'hypotheses_after':trial['output']['tracks'],
             'prediction_p95_before_hz':old['fit_quality']['p95_hz'],
             'prediction_p95_after_hz':trial['fit_quality']['p95_hz'],
             'duration_buckets':{k:{'before':len(before&v),'after':len(after&v),'denominator':len(v)}
                                for k,v in buckets.items()},
             'targets':{str(i):{'before':i in before,'after':i in after} for i in [12,48,51,52]}}
        for match in trial['primary']['matches']:
            target=row['targets'].get(str(match['reference_track_index']))
            if target is not None:
                target.update({k:match[k] for k in ['consistent_source_count',
                    'reference_source_count','in_span_output_purity','output_track_index']})
        rows.append(row)
    device=json.loads((new/'device/receipt.json').read_text())
    arm_runs=[r for r in device['rows'] if r['side']=='arm']
    timing=median(r['reconstruct_s'] for r in arm_runs)
    whole=[json.loads(line) for p in (new/'device').glob('arm-*.stderr')
           for line in p.read_text().splitlines() if line.startswith('{')]
    synthetic=json.loads((new/'synthetic-evaluation.json').read_text())['results'][0]
    result={'rows':rows,'physical':{'tracking_median_s':timing,
            'baseline_tracking_median_s':1.11931,'increase_percent':100*(timing/1.11931-1),
            'within_20_percent_target':timing<=1.11931*1.2,
            'whole_process_median_s':median(r['wall_s'] for r in whole),
            'max_rss_kib':max(r['max_rss_kib'] for r in whole),
            'all_device_outputs_host_identical':all(r['host_byte_identical'] for r in device['rows'])},
            'synthetic':synthetic,
            'qualification_path':str(new),'limits':'Server agreement with explicit ref10 exception; hypothesis bank, not exclusive physical identities'}
    (HERE/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
