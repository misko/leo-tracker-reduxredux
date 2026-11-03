"""Verify archive occurrence selection, record bytes and source accounting."""
import hashlib
import json
from pathlib import Path
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records

HERE=Path(__file__).resolve().parent
path=HERE/'inventory.json';data=json.loads(path.read_text())
for name,h in data['sources'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h
reader=TleArchiveReader(Path('/var/lib/leo/tle'));refs=reader.list_snapshots();by_path={str(r.path):r for r in refs}
parsed={}
for name,snapshot in data['snapshots'].items():
    ref=by_path[name]
    assert ref.provider==snapshot['provider'] and ref.collected_utc_ns==snapshot['collected_utc_ns'] and ref.sha256==snapshot['sha256']
    parsed[name]={r.satellite_number:r for r in parse_element_set_records(reader.read(ref))}
checked=0
for scan in data['scans']:
    eligible=[r for r in refs if r.provider=='space-track' and r.collected_utc_ns<scan['cutoff_utc_ns']]
    latest=max(eligible,key=lambda r:(r.collected_utc_ns,r.sha256));assert str(latest.path)==scan['latest_space_track_path']
    older=max((r for r in refs if r.provider=='space-track' and r.collected_utc_ns<=latest.collected_utc_ns-86400*10**9),key=lambda r:(r.collected_utc_ns,r.sha256))
    assert str(older.path)==scan['older_snapshot_path']
    for row in scan['candidates']:
        for prefix in ('original','older'):
            name=row[prefix+'_snapshot_path'];ref=by_path[name]
            assert ref.collected_utc_ns<scan['cutoff_utc_ns'] and ref.digest==row[prefix+'_snapshot']
            record=parsed[name].get(row['norad'])
            if record:
                actual=hashlib.sha256((record.first_line+'\n'+record.second_line+'\n').encode()).hexdigest()
                assert actual==row[prefix+'_element_sha256']
            else:assert prefix=='older' and not row['available']
        checked+=1
    grouped=[t for g in scan['groups'] for t in g['track_ids']];single=[r['track_id'] for r in scan['singletons']]
    assert len(set(grouped+single))==len(grouped)+len(single)
    assert len(grouped)==scan['summary']['joint_tracks'] and len(single)==scan['summary']['singleton_tracks']
result=dict(verification_pass=True,checked_candidate_occasions=checked,checked_archive_occurrences=len(parsed),
            propagations=0,position_fits=0,outcome_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
with (HERE/'verification.json').open('x') as f:json.dump(result,f,indent=2)
print(json.dumps(result,indent=2))
