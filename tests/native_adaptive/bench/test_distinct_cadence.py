import hashlib

import pytest

from prepare_distinct_arm_cadence import prepare_distinct


def inputs():
    base = {'payloads':dict.fromkeys(['/detector','/manifest','/authority','/obs','/graph','/tle','/seed','/position','/chain'],'a'*64),
        'jobs':{'detector':{'argv':['/detector','/manifest','16','--authority','/authority',
                                   '--observations','/obs','--graph','/graph','--session','baseline']},
                'search':{'argv':['/chain']}},
        'chain':{'output_directory':'/mnt/glrtbench/old/results','stages':[
            {'name':'seeds','argv':['/seed','/obs'],'timeout_s':90},
            {'name':'search','argv':['/position','/obs','/graph','/mnt/glrtbench/old/results/seeds.stdout','/tle'],'timeout_s':360}]},
        'absolute_score_tolerance_hz':1e-9}
    recordings = []
    for i in range(3):
        r = dict(status='complete', session=f'session-{i}', capture_digest=str(i), visits=2215+i)
        r.update({k:f'/mnt/glrtbench/input-{i}/{k}' for k in ('manifest','authority','tle')})
        r['payloads'] = {r[k]:str(i)*64 for k in ('manifest','authority','tle')}
        recordings.append(r)
    return base, recordings


def test_independent_inputs_and_fresh_products():
    base, recordings = inputs()
    files, protocol = prepare_distinct(base, '/mnt/glrtbench/distinct', recordings, 'a'*64, 'b'*64)
    rows = [r.split('\t') for r in files['plan.tsv'].splitlines()]
    for i, r in enumerate(recordings):
        detector = rows[i*2]
        assert detector[6:8] == [r['manifest'], '32']
        assert detector[detector.index('--authority')+1] == r['authority']
        assert detector[detector.index('--session')+1] == r['session']
        chain = protocol['scans'][i]['chain']
        assert chain['stages'][-1]['argv'][4] == r['tle']
        assert chain['stages'][-1]['timeout_s'] == 600
        assert rows[i*2+1][4] == '600'
        assert protocol['period_ms'] == 300000
        assert all(f'/scan-{i}/' in s['argv'][1] for s in chain['stages'])
        assert protocol['payloads'][f'/mnt/glrtbench/distinct/scan-{i}/chain.sh'] == hashlib.sha256(files[f'scan-{i}/chain.sh'].encode()).hexdigest()
    assert base['jobs']['detector']['argv'][2] == '16'


@pytest.mark.parametrize('failure', ['duplicate', 'partial', 'unpinned'])
def test_invalid_recordings(failure):
    base, recordings = inputs()
    if failure == 'duplicate': recordings[1]['session'] = recordings[0]['session']
    if failure == 'partial': recordings[1]['status'] = 'partial'
    if failure == 'unpinned': recordings[1]['payloads'].pop(recordings[1]['tle'])
    with pytest.raises(ValueError):
        prepare_distinct(base, '/mnt/glrtbench/distinct', recordings, 'a'*64, 'b'*64)
