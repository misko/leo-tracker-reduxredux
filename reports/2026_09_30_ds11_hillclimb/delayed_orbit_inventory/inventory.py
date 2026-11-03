"""Read-only availability of orbit updates by scan start plus four hours.

This is explicitly offline information. No propagation, position, measured
frequency, fitted identity or reference coordinate enters this inventory.
"""
import hashlib
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
HILL = HERE.parent
ROOT = HILL.parents[1]
BASE = HILL.parent/'2026_09_30_ds11_single10'
sys.path.insert(0, str(HILL.parent/'2026_09_29_orbit_revision_support'))
from inventory import epoch_ns


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records
    plan_path = BASE/'plan.json'
    identity_path = HILL/'source_balance/catalogue_identities.json'
    plan = json.loads(plan_path.read_text())
    identity = json.loads(identity_path.read_text())
    assert identity['plan_sha256'] == digest(plan_path)
    reader = TleArchiveReader(Path('/var/lib/leo/tle'))
    refs = reader.list_snapshots()
    cache, snapshots, scans, hashes = {}, {}, [], {}

    def records(ref):
        if ref.digest not in cache:
            parsed = parse_element_set_records(reader.read(ref))
            cache[ref.digest] = {r.satellite_number: (epoch_ns(r.first_line),
                hashlib.sha256((r.first_line+'\n'+r.second_line+'\n').encode()).hexdigest())
                for r in parsed}
            assert len(cache[ref.digest]) == len(parsed)
            snapshots[ref.digest] = dict(provider=ref.provider, collected_utc_ns=ref.collected_utc_ns)
        return cache[ref.digest]

    def choose(number, sources):
        options = [(records(r)[number][0], r.collected_utc_ns, r.digest, records(r)[number][1])
                   for r in sources if number in records(r)]
        return max(options, key=lambda v: v[:3]) if options else None

    for index, entry in enumerate(plan['inputs']):
        observation = next(Path(a['path']) for a in entry['artifacts'] if a['kind'] == 'observations')
        manifest_path = next(Path(a['path']) for a in entry['artifacts']
                             if a['kind'] == 'candidates' and a['path'].endswith('.json'))
        side = identity['scans'][str(index)]
        assert side['observation_sha256'] == digest(observation)
        assert side['manifest_sha256'] == digest(manifest_path)
        start = json.loads(observation.read_text())['start_utc_ns']
        manifest = json.loads(manifest_path.read_text())
        original = [next(r for r in refs if r.provider == s['provider'] and
                         r.collected_utc_ns == s['collected_utc_ns'] and r.digest == s['snapshot_sha256'])
                    for s in manifest['provider_sources']]
        cutoff = start+4*3600*10**9
        delayed = [max((r for r in refs if r.provider == provider and r.collected_utc_ns <= cutoff),
                       key=lambda r: (r.collected_utc_ns, r.digest))
                   for provider in sorted({r.provider for r in original})]
        numbers = sorted({number for t in side['tracks'].values() for number in t['candidate_norad']})
        rows = []
        for number in numbers:
            before = choose(number, original)
            assert before is not None
            after = choose(number, delayed)
            fallback = after is None or after[0] < before[0]
            if fallback:
                after = before
            rows.append(dict(norad=number, original_epoch_ns=before[0], delayed_epoch_ns=after[0],
                             original_element_sha256=before[3], delayed_element_sha256=after[3],
                             original_snapshot=before[2], delayed_snapshot=after[2],
                             fallback=fallback, changed=before[3] != after[3]))
        scans.append(dict(index=index, session=entry['session_id'], start_utc_ns=start,
                          cutoff_utc_ns=cutoff, candidates=rows,
                          changed=sum(r['changed'] for r in rows),
                          median_original_absolute_epoch_age_days=statistics.median(abs(start-r['original_epoch_ns'])/86400e9 for r in rows),
                          median_delayed_absolute_epoch_age_days=statistics.median(abs(start-r['delayed_epoch_ns'])/86400e9 for r in rows)))
        for path in (observation, manifest_path):
            hashes[str(path)] = digest(path)
    for path in (Path(__file__), plan_path, identity_path,
                 HILL.parent/'2026_09_29_orbit_revision_support/inventory.py'):
        hashes[str(path)] = digest(path)
    result = dict(schema='ds11-delayed-orbit-availability/v1', lag_hours=4,
                  status='offline availability only; no causal accuracy claim',
                  scans=scans, snapshots=snapshots, source_sha256=hashes)
    with (HERE/'inventory.json').open('x') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(dict(scans=len(scans), candidate_occasions=sum(len(s['candidates']) for s in scans),
                          changed=sum(s['changed'] for s in scans),
                          median_scan_original_age_days=statistics.median(s['median_original_absolute_epoch_age_days'] for s in scans),
                          median_scan_delayed_age_days=statistics.median(s['median_delayed_absolute_epoch_age_days'] for s in scans))))


if __name__ == '__main__':
    main()
