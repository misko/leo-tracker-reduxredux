"""Adapt the public ALGO06 export without changing its numerical endpoint."""
from pathlib import Path
from algo03_shadow_worker import read, write
from algo06_prepare import prepare as prepare_baseline
from algo06_cache import digest


def prepare(root):
    root = Path(root)
    descriptor = read(root/'descriptor.json')
    for name, expected in descriptor['files'].items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or digest(root/path) != expected.removeprefix('sha256:'):
            raise ValueError('ALGO06 export member changed')
    old = read(root/'algo06-terminal.json')
    z = prepare_baseline(root)
    addition = old['candidate']
    if addition:
        target = next(t for t in z['targets'] if t['observation_ids'] == addition['target_ids'])
        trial = 'published_ALGO06'
        result = dict(decisions={'72h_30s':dict(status='qualified', trial=trial, source=target['fragment_id'])},
                      trials={trial:addition['trial']})
        write(root/'screen/SCAN/result.json', dict(targets=[dict(source=target,summaries=[addition['screen']])]))
    else:
        result = dict(decisions={'72h_30s':dict(status='fallback')}, trials={})
    write(root/'position/SCAN/result.json', result)
    write(root/'exports/SCAN/published-algo06.json', old)
    return z

