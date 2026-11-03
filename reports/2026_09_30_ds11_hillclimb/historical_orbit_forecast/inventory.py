"""Freeze historical orbit triplets and disjoint calibration/validation scope."""
import hashlib
import inspect
import json
from pathlib import Path
import sys
import time
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records
HERE=Path(__file__).resolve().parent;HILL=HERE.parent
sys.path.insert(0,str(HILL.parent/'2026_09_29_orbit_revision_support'))
from inventory import epoch_ns


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    started=time.monotonic();geometry_path=HILL/'joint_receiver_association/causal-calibration-geometry.polished.json'
    cutoff=json.loads(geometry_path.read_text())['cutoff_utc_ns'];day=86400*10**9
    anchor=((cutoff-2*day)//day)*day;centers=[anchor-(11-i)*day for i in range(12)]
    reader=TleArchiveReader(Path('/var/lib/leo/tle'));refs=reader.list_snapshots()
    available={str(r.path):max(r.collected_utc_ns,r.path.stat().st_mtime_ns) for r in refs}
    refs=[r for r in refs if available[str(r.path)]<=cutoff-day]
    providers=('huggingface','space-track');cache={};sources={str(p):digest(p) for p in (Path(__file__),HERE/'PROTOCOL.md',geometry_path,Path(inspect.getfile(epoch_ns)),Path(inspect.getfile(parse_element_set_records)))};occurrences={}
    def combined(deadline):
        chosen=[max((r for r in refs if r.provider==provider and available[str(r.path)]<=deadline),key=lambda r:(r.collected_utc_ns,r.digest)) for provider in providers]
        mapping={}
        for ref in chosen:
            if ref.digest not in cache:
                text=reader.read(ref);assert hashlib.sha256(text.encode()).hexdigest()==ref.sha256
                records=parse_element_set_records(text);cache[ref.digest]={r.satellite_number:r for r in records};assert len(cache[ref.digest])==len(records)
            sources[str(ref.path)]=digest(ref.path)
            occurrences[str(ref.path)]=dict(provider=ref.provider,collected_utc_ns=ref.collected_utc_ns,local_mtime_ns=ref.path.stat().st_mtime_ns,available_proxy_utc_ns=available[str(ref.path)],sha256=ref.sha256)
            for number,r in cache[ref.digest].items():
                epoch=epoch_ns(r.first_line);key=(epoch,ref.collected_utc_ns,ref.digest)
                if number not in mapping or key>mapping[number]['key']:
                    mapping[number]=dict(key=key,epoch=epoch,name=r.name,first_line=r.first_line,second_line=r.second_line,archive_path=str(ref.path),available_proxy_utc_ns=available[str(ref.path)])
        return mapping
    windows=[]
    for ordinal,center in enumerate(centers):
        old,current,later=[combined(center+offset*day) for offset in (-1,0,1)]
        roster={n for n,r in current.items() if r['name'].upper().startswith('STARLINK-') and 'DEB' not in r['name'].upper()}
        common=roster & old.keys() & later.keys();selected=sorted(common,key=lambda n:hashlib.sha256(str(n).encode()).digest())[:256]
        cases=[];excluded={'no_previous_epoch_advance':0,'no_reference_epoch_advance':0}
        for number in selected:
            if current[number]['epoch']<=old[number]['epoch']:excluded['no_previous_epoch_advance']+=1;continue
            if later[number]['epoch']<=current[number]['epoch']:excluded['no_reference_epoch_advance']+=1;continue
            parity=int(hashlib.sha256(str(number).encode()).hexdigest(),16)%2
            split='training' if ordinal<8 and parity==0 else 'validation' if ordinal>=8 and parity==1 else 'unused'
            if split=='training':assert later[number]['available_proxy_utc_ns']<=centers[8]
            cases.append(dict(norad=number,split=split,old=old[number],current=current[number],later=later[number]))
        windows.append(dict(ordinal=ordinal,center_utc_ns=center,roster=len(roster),missing_triplet_objects=len(roster-common),sampled=len(selected),excluded=excluded,cases=cases))
    train={c['norad'] for w in windows for c in w['cases'] if c['split']=='training'};validation={c['norad'] for w in windows for c in w['cases'] if c['split']=='validation'};assert not train & validation
    result=dict(cutoff_utc_ns=cutoff,maximum_snapshot_availability_proxy_utc_ns=max(r['available_proxy_utc_ns'] for r in occurrences.values()),windows=windows,archive_occurrences=occurrences,sources=sources,independent_orbit_truth=False,elapsed_s=time.monotonic()-started)
    with (HERE/'inventory.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(windows=len(windows),cases=sum(len(w['cases']) for w in windows),training_objects=len(train),validation_objects=len(validation),archive_occurrences=len(occurrences),elapsed_s=result['elapsed_s'])),flush=True)


if __name__=='__main__':main()
