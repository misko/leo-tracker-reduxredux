"""Metadata-only DS11 older-orbit coverage using the trained prior's convention."""
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
HILL=HERE.parent
ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('revision_inventory',HILL.parent/'2026_09_29_orbit_revision_support/inventory.py')
historical=importlib.util.module_from_spec(spec);spec.loader.exec_module(historical)
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def element_digest(record):return hashlib.sha256((record.first_line+'\n'+record.second_line+'\n').encode()).hexdigest()
def common_support(group,mapping):
    sets=[set(mapping[tid]['candidate_norad']) for tid in group['track_ids']]
    common=set.intersection(*sets)
    assert group['norad'] in common and len(common)==group['common_candidate_norads']
    return sorted(common)
def main():
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records
    start=time.monotonic();sources={}
    paths=[HILL/'delayed_orbit_inventory/inventory.json',HILL/'source_balance/catalogue_identities.json',HILL/'joint_identity/overlap.json']
    seed,identity,overlap=[json.loads(p.read_text()) for p in paths]
    for obj in (seed,overlap):
        for name,h in obj.get('source_sha256',{}).items():
            p=Path(name);p=p if p.is_absolute() else ROOT/p
            assert digest(p)==h.removeprefix('sha256:');sources[str(p)]=h.removeprefix('sha256:')
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));refs=archive.list_snapshots();by_digest={r.digest:r for r in refs}
    st=[r for r in refs if r.provider=='space-track'];cache={};snapshots={}
    def records(ref):
        if ref.digest not in cache:
            parsed=parse_element_set_records(archive.read(ref));mapping={r.satellite_number:r for r in parsed}
            assert len(mapping)==len(parsed)
            cache[ref.digest]=mapping
            snapshots[ref.digest]=dict(path=str(ref.path),provider=ref.provider,collected_utc_ns=ref.collected_utc_ns,sha256=ref.sha256)
        return cache[ref.digest]
    scans=[]
    for index in (0,16):
        scan=next(s for s in seed['scans'] if s['index']==index)
        cutoff=scan['start_utc_ns']-505*10**9
        latest=historical.select(st,cutoff)
        assert latest is not None
        old=historical.select(st,latest.collected_utc_ns-86400*10**9,False)
        assert old is not None and old.collected_utc_ns<cutoff
        old_records=records(old);records(latest)
        rows=[]
        for c in scan['candidates']:
            ref=by_digest[c['original_snapshot']];assert ref.collected_utc_ns<cutoff
            original=records(ref)[c['norad']]
            assert element_digest(original)==c['original_element_sha256']
            assert historical.epoch_ns(original.first_line)==c['original_epoch_ns']
            older=old_records.get(c['norad'])
            rows.append(dict(norad=c['norad'],original_snapshot=c['original_snapshot'],original_element_sha256=c['original_element_sha256'],
                             original_epoch_ns=c['original_epoch_ns'],older_snapshot=old.digest,
                             older_element_sha256=element_digest(older) if older else None,
                             older_epoch_ns=historical.epoch_ns(older.first_line) if older else None,
                             available=older is not None,changed=older is not None and element_digest(older)!=c['original_element_sha256']))
        frozen=next(s for s in overlap['scans'] if s['index']==index);mapping=identity['scans'][str(index)]['tracks']
        assert scan['session']==frozen['session_id']==identity['scans'][str(index)]['session_id']
        assert set(c['norad'] for c in rows)==set(n for t in mapping.values() for n in t['candidate_norad'])
        groups=[];used=set()
        for g in frozen['groups']:
            common=common_support(g,mapping);assert not used.intersection(g['track_ids']);used.update(g['track_ids'])
            groups.append(dict(selected_norad=g['norad'],track_ids=g['track_ids'],candidate_norad=common))
        singles=[dict(track_id=tid,candidate_norad=t['candidate_norad']) for tid,t in mapping.items() if tid not in used]
        assert len(used)+len(singles)==frozen['tracks']
        status={r['norad']:r for r in rows}
        summary=dict(all_candidates=len(rows),available=sum(r['available'] for r in rows),changed=sum(r['changed'] for r in rows),
                     joint_groups=len(groups),joint_tracks=len(used),singleton_tracks=len(singles),
                     common_candidate_hypotheses=sum(len(g['candidate_norad']) for g in groups),
                     selected_group_sources_changed=sum(status[g['selected_norad']]['changed'] for g in groups))
        scans.append(dict(index=index,session_id=scan['session'],start_utc_ns=scan['start_utc_ns'],cutoff_utc_ns=cutoff,
                          latest_space_track_snapshot=latest.digest,older_snapshot=old.digest,summary=summary,
                          candidates=rows,groups=groups,singletons=singles))
    paths.extend([Path(__file__),HERE/'test_run.py',HERE/'PROTOCOL.md',Path(historical.__file__),Path(inspect.getfile(TleArchiveReader)),Path(inspect.getfile(parse_element_set_records))])
    for p in paths:sources[str(p)]=digest(p)
    output=dict(scans=scans,snapshots=snapshots,sources=sources,position_fits=0,propagations=0,reference_used=False,elapsed_s=time.monotonic()-start)
    with (HERE/'inventory.json').open('x') as f:json.dump(output,f,indent=2)
    print(json.dumps(dict(scans=[dict(index=s['index'],**s['summary']) for s in scans],snapshots=len(snapshots),elapsed_s=output['elapsed_s']),indent=2))
if __name__=='__main__':main()

