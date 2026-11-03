"""Render a fixed-cadence replay with independent recording and TLE authorities."""
import copy
import hashlib
import json

from prepare_arm_cadence import prepare
from render_arm_chain import render


def prepare_distinct(base, remote, recordings, detector_sha, controller_sha):
    if len({r['session'] for r in recordings}) != len(recordings):
        raise ValueError('distinct recording sessions required')
    base = copy.deepcopy(base)
    base['jobs']['detector']['argv'][2] = '32'
    files, protocol = prepare(base, remote, len(recordings), detector_sha, controller_sha, 5000)
    payloads = protocol['payloads']
    old_detector = base['jobs']['detector']['argv']
    for path in (old_detector[1], old_detector[old_detector.index('--authority')+1],
                 base['chain']['stages'][-1]['argv'][4]):
        payloads.pop(path)
    rows = [line.split('\t') for line in files['plan.tsv'].splitlines()]
    for i, recording in enumerate(recordings):
        if recording['status'] != 'complete' or recording['visits'] <= 0:
            raise ValueError('complete staged recording required')
        for key in ('manifest', 'authority', 'tle'):
            if recording[key] not in recording['payloads']:
                raise ValueError('recording authority must be pinned')
        for path, digest in recording['payloads'].items():
            if path in payloads and payloads[path] != digest:
                raise ValueError('conflicting input digest')
            payloads[path] = digest
        row = next(row for row in rows if row[:2] == ['detector', str(i)])
        row[6] = recording['manifest']
        row[row.index('--authority')+1] = recording['authority']
        row[row.index('--session')+1] = recording['session']
        scan = protocol['scans'][i]
        scan['recording'] = {k: recording[k] for k in ('session', 'capture_digest', 'visits')}
        scan['chain']['stages'][-1]['argv'][4] = recording['tle']
        # Finish a slow recording for scientific comparison while separately
        # enforcing the unchanged 300-second throughput acceptance criterion.
        scan['chain']['stages'][-1]['timeout_s'] = 600
        next(r for r in rows if r[:2] == ['downstream', str(i)])[4] = '600'
        name = f'scan-{i}/chain.sh'
        files[name] = render(scan['chain'], payloads)
        payloads[remote+'/'+name] = hashlib.sha256(files[name].encode()).hexdigest()
    for row in rows:
        if any(any(c in value for c in '\t\r\n\0') for value in row):
            raise ValueError('unsafe plan field')
    files['plan.tsv'] = '\n'.join('\t'.join(row) for row in rows)+'\n'
    payloads[remote+'/plan.tsv'] = hashlib.sha256(files['plan.tsv'].encode()).hexdigest()
    protocol['scope'] = ('Three distinct recorded captures at fixed 300-second replay cadence; '
                         'original scientific UTC and per-capture TLE retained; no live RF qualification')
    return files, protocol
