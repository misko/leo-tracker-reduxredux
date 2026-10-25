"""Artifact-only adjacent-residual summaries; no fitting or source changes."""
import csv
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
path=HERE/'point_diagnostics.csv'
rows=list(csv.DictReader(path.open()))
groups={}
for row in rows:groups.setdefault((row['component'],int(row['degree'])),[]).append(row)
output=[]
for (component,degree),values in groups.items():
    changes=[]
    for before,after in zip(values[:-1],values[1:]):
        change=float(after['residual_hz'])-float(before['residual_hz'])
        changes.append(dict(before_ID=before['observation_id'],after_ID=after['observation_id'],
            before_time_s=float(before['time_s']),after_time_s=float(after['time_s']),
            change_hz=change,gap_s=float(after['time_s'])-float(before['time_s'])))
    changes.sort(key=lambda row:(-abs(row['change_hz']),row['after_time_s']))
    longest=run=1
    for before,after in zip(values[:-1],values[1:]):
        run=run+1 if (float(before['residual_hz'])>0)==(float(after['residual_hz'])>0) else 1
        longest=max(longest,run)
    output.append(dict(component=component,degree=degree,largest_adjacent_changes=changes[:5],
                       longest_same_sign_run=longest))
with (HERE/'adjacent_summary.json').open('x') as stream:
    json.dump(dict(rows=output,point_CSV_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        no_new_polynomial_or_candidate_fits=True),stream,indent=2)
    stream.write('\n')
