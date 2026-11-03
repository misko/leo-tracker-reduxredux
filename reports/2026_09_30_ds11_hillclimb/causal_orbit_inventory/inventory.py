"""Metadata-only audit of causal historical element retention and 505s guard."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
HILL = HERE.parent
sys.path.insert(0, str(HILL.parent/'2026_09_29_orbit_revision_support'))
from inventory import epoch_ns


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records
    seed_path = HILL/'delayed_orbit_inventory/inventory.json'
    seed = json.loads(seed_path.read_text())
    for path, sha in seed['source_sha256'].items():
        assert digest(path) == sha, path
    wanted = {r['norad'] for s in seed['scans'] for r in s['candidates']}
    original_snapshots = {r['original_snapshot'] for s in seed['scans'] for r in s['candidates']}
    earliest = min(s['start_utc_ns'] for s in seed['scans'])-3*86400*10**9
    latest = max(s['start_utc_ns'] for s in seed['scans'])
    reader = TleArchiveReader(Path('/var/lib/leo/tle'))
    refs = sorted((r for r in reader.list_snapshots()
                   if earliest <= r.collected_utc_ns < latest or r.digest in original_snapshots),
                  key=lambda r: (r.collected_utc_ns, r.digest))
    queries = sorted((s['start_utc_ns']-delay, stage, s)
                     for s in seed['scans'] for stage, delay in
                     [('same_guard', 505*10**9), ('capture_start', 0)])
    best, snapshots, scans = {}, {}, []
    cursor = 0
    for cutoff, stage, scan in queries:
        while cursor < len(refs) and refs[cursor].collected_utc_ns < cutoff:
            ref = refs[cursor]
            snapshots[ref.digest] = dict(provider=ref.provider, collected_utc_ns=ref.collected_utc_ns)
            for record in parse_element_set_records(reader.read(ref)):
                number = record.satellite_number
                if number not in wanted:
                    continue
                epoch = epoch_ns(record.first_line)
                sha = hashlib.sha256((record.first_line+'\n'+record.second_line+'\n').encode()).hexdigest()
                value = (epoch, ref.collected_utc_ns, ref.digest, sha)
                if number not in best or value[:3] > best[number][:3]:
                    best[number] = value
            cursor += 1
        rows = []
        for row in scan['candidates']:
            old_ref = seed['snapshots'][row['original_snapshot']]
            assert old_ref['collected_utc_ns'] < cutoff
            old = (row['original_epoch_ns'], old_ref['collected_utc_ns'],
                   row['original_snapshot'], row['original_element_sha256'])
            selected = max(old, best.get(row['norad'], old), key=lambda v: v[:3])
            assert selected[1] < cutoff
            rows.append(dict(norad=row['norad'], original_epoch_ns=old[0],
                             selected_epoch_ns=selected[0], original_element_sha256=old[3],
                             selected_element_sha256=selected[3], selected_snapshot=selected[2],
                             changed=old[3] != selected[3], epoch_advance_s=(selected[0]-old[0])/1e9))
        scans.append(dict(index=scan['index'], session=scan['session'], stage=stage,
                          start_utc_ns=scan['start_utc_ns'], cutoff_utc_ns=cutoff, candidates=rows))
    summaries = {}
    for stage in ('same_guard', 'capture_start'):
        groups = [s for s in scans if s['stage'] == stage]
        rows = [r for s in groups for r in s['candidates']]
        summaries[stage] = dict(scans=len(groups), candidate_occasions=len(rows),
                                changed=sum(r['changed'] for r in rows),
                                newer_epochs=sum(r['epoch_advance_s'] > 0 for r in rows),
                                scans_changed=sum(any(r['changed'] for r in s['candidates']) for s in groups))
    result = dict(schema='ds11-causal-orbit-availability/v1', lookback_days=3,
                  status='metadata only; no propagation, measurements or position fit',
                  summaries=summaries, scans=scans, snapshots=snapshots,
                  source_sha256={str(p): digest(p) for p in (Path(__file__), seed_path,
                      HILL.parent/'2026_09_29_orbit_revision_support/inventory.py')})
    with (HERE/'inventory.json').open('x') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
