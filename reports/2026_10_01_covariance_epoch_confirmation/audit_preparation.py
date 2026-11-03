"""Bind prepared observations and causal state banks before model execution."""
import json
from pathlib import Path
from prepare import digest, publication_times, units, write_new

HERE = Path(__file__).resolve().parent

def audit():
    journal = HERE / 'tle-publications.jsonl'
    publications = publication_times(journal)
    rows = []
    for selected in units():
        unit = selected['unit_id']
        launch = json.loads((HERE / 'preparation' / f'{unit}.json').read_text())
        if launch['returncode'] != 0: raise ValueError(f'preparation failed: {unit}')
        ep = HERE / 'evidence' / f'{unit}.json'
        op = HERE / 'evidence' / f'{unit}-orbits.json'
        e, o = json.loads(ep.read_text()), json.loads(op.read_text())
        if e['session_id'] != selected['session_id'] or e['manifest_sha256'] != selected['manifest_sha256']: raise ValueError('capture binding')
        if digest(e['source']['path']) != e['source']['sha256']: raise ValueError('observation hash')
        source = json.loads(Path(e['source']['path']).read_text())
        cutoff = min(source['start_utc_ns'], selected.get('capture_start_earliest_utc_ns', selected['capture_start_utc_ns']))
        if o['session_id'] != e['session_id'] or o['observation_sha256'] != e['source']['sha256']: raise ValueError('orbit binding')
        if not o['tle']['causal'] or digest(o['state_file']) != o['state_sha256']: raise ValueError('state bank')
        if o['tle']['publication_log_sha256'] != digest(journal): raise ValueError('journal hash')
        for proof in o['tle']['sources']:
            if proof['cutoff_utc_ns'] != cutoff: raise ValueError('capture cutoff')
            if not max(proof['collected_utc_ns'], proof['mtime_ns']) <= proof['published_utc_ns'] < cutoff: raise ValueError('noncausal snapshot')
            if proof['published_utc_ns'] not in publications[(proof['provider'], proof['sha256'])]: raise ValueError('missing publication')
        rows.append({'unit': unit, 'dataset': unit.split('-')[0], 'tracks': len(e['tracks']), 'propagated_satellites': o['propagated_count'], 'evidence_sha256': digest(ep), 'orbit_metadata_sha256': digest(op)})
    if len(rows) != 32: raise ValueError('wrong panel size')
    write_new(HERE / 'preparation-audit.json', {'all_32_passed': True, 'rows': rows})
    print(json.dumps({'passed': True, 'units': len(rows), 'tracks': sum(r['tracks'] for r in rows)}))

if __name__ == '__main__': audit()
