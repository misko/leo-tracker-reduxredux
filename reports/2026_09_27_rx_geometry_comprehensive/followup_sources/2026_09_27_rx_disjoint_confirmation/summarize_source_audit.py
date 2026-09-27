"""Summarize fixed source audits without changing any fitted model."""
import hashlib
import json
from pathlib import Path
from source_continuity_math import alias_check,cross_channel_difference

HERE=Path(__file__).resolve().parent


def main():
    output={};bindings={}
    for sid in ('scan-fw-127d8fc36e804ae2','scan-fw-8f4f960d9db67798'):
        path=HERE/f'source-audit-{sid}.json';raw=path.read_bytes();bindings[path.name]=hashlib.sha256(raw).hexdigest();d=json.loads(raw)
        tracks=[]
        for t in d['tracks']:
            tracks.append({'track_id':t['track_id'],'observations':t['observations'],'span_s':t['span_s'],
                'channel_edge_counts':t['channel_edge_counts'],'rf_transitions':t['rf_transitions'],
                'largest_gap_s':t['largest_gaps'][0]['dt_s'],**alias_check(t['rows'])})
        output[sid]={'tracks':tracks}
        if sid=='scan-fw-8f4f960d9db67798':
            a,b=d['tracks'];output[sid]['cross_channel']={
                'left_track':a['track_id'],'right_track':b['track_id'],
                'left_to_right':cross_channel_difference(a['rows'],b['rows']),
                'right_to_left':cross_channel_difference(b['rows'],a['rows'])}
    out={'scope':'Posthoc continuity diagnostic. Alias arithmetic parity does not prove chosen alias/path physically correct; interpolation is not a drift estimator.',
         'source_sha256':bindings,'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),HERE/'source_continuity_math.py')},'results':output}
    with (HERE/'source-audit-summary.json').open('x') as stream:json.dump(out,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
