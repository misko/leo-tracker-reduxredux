"""Adapt explicit saved native-GLRT batches to reusable observation checkpoints.

This archive adapter retains the published full-scan identity recipe. Other
detectors use the pure projection API with their own explicit analysis identity.
"""
import argparse
from pathlib import Path

from leo.contracts.digests import canonical_digest
from leo.native_pipeline import membership as m
from leo.native_pipeline.projection import WindowAuthority, project_integer_candidates
from leo.native_pipeline.runner import digest, finite_json, write_json
import json


def project(archive, output, capture_digest):
    archive, output = Path(archive),Path(output)
    completion = finite_json(archive/'completion.json')
    if completion['status'] != 'PASS':
        raise ValueError('incomplete detector archive')
    manifest = finite_json(archive/'capture-manifest.json')
    if canonical_digest(manifest) != capture_digest:
        raise ValueError('capture manifest digest mismatch')
    inventory = finite_json(archive/'inventory.json')
    events = manifest['receipt']['events']
    if len(events) != len(inventory) or any(i['event'] != e for i,e in zip(inventory,events)):
        raise ValueError('capture inventory mismatch')
    batches = sorted(archive.glob('batch-*.jsonl'))
    calls = {}
    for path in batches:
        begin = int(path.stem.split('-')[1])
        for line in path.read_text().splitlines():
            document = json.loads(line)
            if 'result' not in document:
                continue
            call = document['result']
            visit = begin+call['sequence']
            if visit in calls:
                raise ValueError('duplicate visit')
            calls[visit] = call
    if set(calls) != set(range(len(events))):
        raise ValueError('missing or unexpected detector visits')
    analysis = canonical_digest({'algorithm':'coarse-gate-disabled-full-scan-v1',
        'completion':digest(archive/'completion.json'),'inventory':digest(archive/'inventory.json'),
        'batches':[(p.name,digest(p)) for p in batches]})
    rate = manifest['receipt']['plan']['geometry']['sample_rate_hz']
    timing = manifest['timing']
    observations = ['\t'.join(m.OBSERVATION_HEADER)]
    mapping = ['\t'.join(m.SOURCE_HEADER)]
    supports = []
    for visit,call in sorted(calls.items()):
        event = events[visit]
        if call['rate_hz'] != rate or event['visit_index'] != visit:
            raise ValueError('detector geometry mismatch')
        seen = set()
        if call['stride_ms'] <= 0 or call['dwell_ms'] < 20:
            raise ValueError('invalid detector probe cadence')
        positions = list(range(0,call['dwell_ms']-20+1,call['stride_ms']))
        expected_rows = {(rx,p) for rx in manifest['receipt']['plan']['geometry']['receiver_ids']
                         for p in range(len(positions))}
        for row in call['rows']:
            rx,probe = row['receiver_id'],row['probe_index']
            if (rx,probe) not in expected_rows or row['probe_start_ms'] != positions[probe]:
                raise ValueError('unexpected detector receiver/probe')
            if (rx,probe) in seen:
                raise ValueError('duplicate receiver/probe')
            seen.add((rx,probe))
            first = event['valid_start_counter']+round(row['probe_start_ms']*rate/1000)
            count = rate//50
            if first < event['valid_start_counter'] or first+count > event['valid_end_counter_exclusive']:
                raise ValueError('probe extends beyond dwell')
            a = WindowAuthority(capture_digest,analysis,visit,rx,probe,event['target']['channel'],
                event['target']['edge'],float(event['target']['rf_center_hz']-event['actual_if_offset_hz']),
                rate,count,first,timing['session_start_device_sample_counter'],timing['first_sample_estimate_utc_ns'])
            for p in project_integer_candidates(a,row['candidates']):
                observations.append('\t'.join(map(str,p.observation)))
                mapping.append('\t'.join(map(str,p.source)))
                supports.append({'candidate_id':p.observation[0],
                    'source_start_counter':first+p.support.start,'source_end_counter':first+p.support.end,
                    'factorial_support_moments_s':p.support.moments})
        if seen != expected_rows:
            raise ValueError('missing detector receiver/probe')
    output.mkdir(parents=True,exist_ok=False)
    (output/'observations.tsv').write_text('\n'.join(observations)+'\n')
    (output/'candidate-map.tsv').write_text('\n'.join(mapping)+'\n')
    write_json(output/'support.json',supports)
    obs = m.read_observations(output/'observations.tsv')
    m.read_sources(output/'candidate-map.tsv',obs)
    receipt = {'status':'complete','observations':len(obs),'visits':len(calls),
               'capture_digest':capture_digest,'analysis_digest':analysis,
               'observation_sha256':digest(output/'observations.tsv'),
               'source_map_sha256':digest(output/'candidate-map.tsv')}
    receipt['support_sha256'] = digest(output/'support.json')
    receipt['adapter_sha256'] = digest(__file__)
    from leo.native_pipeline import projection
    receipt['projector_sha256'] = digest(projection.__file__)
    write_json(output/'receipt.json',receipt)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--capture-digest',required=True)
    args = parser.parse_args()
    print(json.dumps(project(args.archive,args.output,args.capture_digest)))
