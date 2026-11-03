"""Separate changed TLE bytes from changed SGP4 inputs, without propagation."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDS = ('jdsatepoch', 'jdsatepochF', 'bstar', 'ndot', 'nddot',
          'inclo', 'nodeo', 'ecco', 'argpo', 'mo', 'no_kozai')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    from sgp4.api import Satrec
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records
    inventory_path = HERE/'inventory.json'
    inventory = json.loads(inventory_path.read_text())
    seed_path = HERE.parent/'delayed_orbit_inventory/inventory.json'
    seed = json.loads(seed_path.read_text())
    for path, sha in inventory['source_sha256'].items():
        assert digest(path) == sha
    reader = TleArchiveReader(Path('/var/lib/leo/tle'))
    refs = {r.digest: r for r in reader.list_snapshots()}
    old_rows = {(s['index'], r['norad']): r for s in seed['scans'] for r in s['candidates']}
    cache = {}

    def parameters(snapshot, number, expected):
        if snapshot not in cache:
            cache[snapshot] = {r.satellite_number: r for r in parse_element_set_records(reader.read(refs[snapshot]))}
        record = cache[snapshot][number]
        assert hashlib.sha256((record.first_line+'\n'+record.second_line+'\n').encode()).hexdigest() == expected
        satellite = Satrec.twoline2rv(record.first_line, record.second_line)
        return {name: float(getattr(satellite, name)) for name in FIELDS}

    scans = []
    for scan in inventory['scans']:
        if scan['stage'] != 'capture_start':
            continue
        changes = []
        for row in scan['candidates']:
            if not row['changed']:
                continue
            original = old_rows[scan['index'], row['norad']]
            old = parameters(original['original_snapshot'], row['norad'], row['original_element_sha256'])
            new = parameters(row['selected_snapshot'], row['norad'], row['selected_element_sha256'])
            differences = {name: new[name]-old[name] for name in FIELDS if old[name] != new[name]}
            changes.append(dict(norad=row['norad'], differences=differences,
                                changed_sgp4_inputs=bool(differences)))
        if changes:
            scans.append(dict(index=scan['index'], session=scan['session'],
                              changed_bytes=len(changes), changed_sgp4_inputs=sum(c['changed_sgp4_inputs'] for c in changes),
                              candidates=changes))
    output = dict(schema='ds11-causal-orbit-semantic-audit/v1',
                  limitation='SGP4 field comparison only; no frequency or position accuracy claim',
                  fields=FIELDS, scans=scans,
                  source_sha256={str(p): digest(p) for p in (Path(__file__), inventory_path, seed_path)})
    with (HERE/'semantic_audit.json').open('x') as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
    print(json.dumps([{k:v for k,v in s.items() if k != 'candidates'} for s in scans], indent=2))


if __name__ == '__main__':
    main()
