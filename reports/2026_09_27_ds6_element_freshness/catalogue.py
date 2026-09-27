"""Research-only causal per-object epoch selection, preserving baseline row IDs."""
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_full_cfo'))
from run_baseline import TleArchiveReader,exclude_labelled_starlink_debris,parse_element_sets
from leo.sky.propagation import parse_element_set_records


def choose_records(base_records,sources):
    """Newest element epoch among latest causal provider snapshots; stable ties."""
    choices={}
    for collected,digest,records,epochs in sources:
        for record,epoch in zip(records,epochs,strict=True):
            key=(epoch,collected,digest)
            old=choices.get(record.satellite_number)
            if old is None or key>old[0]:choices[record.satellite_number]=(key,record)
    return [choices[r.satellite_number] for r in base_records]


def catalogues(archive,start_utc_ns,expected_digest,cache=None):
    cache={} if cache is None else cache
    cutoff=start_utc_ns-505_000_000_000
    base=archive.select_latest_before(cutoff)
    assert base.digest==expected_digest
    snapshots=archive.list_snapshots()
    latest=[]
    for provider in sorted({s.provider for s in snapshots}):
        candidates=[s for s in snapshots if s.provider==provider and s.collected_utc_ns<cutoff]
        if candidates:latest.append(max(candidates,key=lambda s:(s.collected_utc_ns,s.sha256)))
    def read(s):
        if s.digest not in cache:
            payload,_=exclude_labelled_starlink_debris(archive.read(s))
            cat=parse_element_sets(payload)
            cache[s.digest]=(list(parse_element_set_records(payload)),cat,cat.element_epoch_utc_ns())
        return cache[s.digest]
    records,old,old_epochs=read(base)
    sources=[]
    for s in latest:
        r,_,epochs=read(s);sources.append((s.collected_utc_ns,s.digest,r,epochs))
    chosen=choose_records(records,sources)
    new=parse_element_sets(''.join(record.text for _,record in chosen))
    assert new.satellite_numbers==old.satellite_numbers
    provenance=dict(cutoff_utc_ns=cutoff,baseline_digest=base.digest,
        providers=[dict(provider=s.provider,collected_utc_ns=s.collected_utc_ns,digest=s.digest) for s in latest],
        changed_rows=[i for i,((key,r),before) in enumerate(zip(chosen,records,strict=True)) if r.text!=before.text],
        element_source=[dict(epoch_utc_ns=key[0],collected_utc_ns=key[1],snapshot_digest=key[2]) for key,_ in chosen])
    return old,new,provenance
