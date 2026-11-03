"""Collect independently evaluated host trials and physical device timings."""
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent


def main():
    rows=[]
    names=['rolling','kalman','linking']
    names += [name for name in ('kalman-v2','linking-v2')
              if (HERE/'qualification'/name/'device/receipt.json').exists()]
    for name in names:
        d=HERE/'qualification'/name
        host=json.loads((d/'receipt.json').read_text())
        device=json.loads((d/'device/receipt.json').read_text())
        synth=json.loads((d/'synthetic-evaluation.json').read_text())['results'][0]
        row={'method':name,'synthetic':synth,
             'device_all_host_identical':all(r['host_byte_identical'] for r in device['rows'])}
        for side in ('arm','server'):
            score=json.loads((d/f'{side}-evaluation.json').read_text())
            run=next(c for c in host['cases'] if c['side']==side)
            device_rows=[r for r in device['rows'] if r['side']==side]
            whole=[json.loads(line) for p in (d/'device').glob(f'{side}-*.stderr')
                   for line in p.read_text().splitlines() if line.startswith('{')]
            row[side]={'represented':score['reviewed']['represented_count'],
                'hypotheses':score['output']['tracks'],
                'one_to_one_original':score['primary']['complete_one_to_one_count'],
                'unmatched_outputs_original':len(score['primary']['unmatched_output_indexes']),
                'missing':score['reviewed']['missing_indexes'],
                'focus':score['reviewed']['focus_represented'],
                'prediction_p95_hz':score['fit_quality']['p95_hz'],
                'prediction_samples':score['fit_quality']['evaluated_predictions'],
                'host_tracking_median_s':median(r['reconstruct_s'] for r in run['repetitions']),
                'arm_tracking_median_s':median(r['reconstruct_s'] for r in device_rows),
                'arm_whole_process_median_s':median(r['wall_s'] for r in whole),
                'arm_max_rss_kib':max(r['max_rss_kib'] for r in whole)}
        rows.append(row)
    (HERE/'summary.json').write_text(json.dumps(rows,indent=2)+'\n')
    for row in rows:
        print(row['method'],json.dumps(row['arm']), 'serverinput',row['server']['represented'],
              'synthetic',row['synthetic']['complete_true_curves'])


if __name__=='__main__':
    main()
