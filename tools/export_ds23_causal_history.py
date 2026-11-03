"""Read-only pre-scan TLE history export for one DS23 case; JSON to stdout."""

import argparse
import json
from pathlib import Path

from sgp4.exporter import export_tle

from run_algo01_ds23_sample import OUT as SOURCE,read,sha
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


def distinct_epochs(versions,minimum_gap_ns=1_000_000_000):
    """Keep newest-to-oldest genuine epochs; prefer first causal publication."""
    by_epoch={}
    for row in sorted(versions,key=lambda r:r['collected_utc_ns']):
        by_epoch.setdefault(row['epoch'],row)
    kept=[]
    for row in sorted(by_epoch.values(),key=lambda r:-r['epoch']):
        if not kept or kept[-1]['epoch']-row['epoch']>=minimum_gap_ns:kept.append(row)
    return kept[::-1]


def export(case):
    directory=SOURCE/case
    receipt=read(directory/'receipt.json');elements=read(directory/'nominal_elements.json')
    cutoff=receipt['cutoff_utc_ns'];reader=TleArchiveReader(Path('/var/lib/leo/tle'))
    snapshots=[s for s in reader.list_snapshots('space-track')
               if cutoff-72*3600*1_000_000_000<=s.collected_utc_ns<=cutoff]
    unique={}
    for s in snapshots:
        if s.sha256 not in unique or s.collected_utc_ns<unique[s.sha256].collected_utc_ns:unique[s.sha256]=s
    history={n:[] for n in elements}
    sources=[]
    for s in sorted(unique.values()):
        cat=parse_element_sets(reader.read(s))
        sources.append(dict(collected_utc_ns=s.collected_utc_ns,sha256=s.sha256))
        for n,satellite,epoch in zip(cat.satellite_numbers,cat.satellites,cat.element_epoch_utc_ns(),strict=True):
            if str(n) not in elements or epoch>cutoff:continue
            history[str(n)].append(dict(lines=list(export_tle(satellite)),epoch=int(epoch),
                collected_utc_ns=s.collected_utc_ns,snapshot_sha256=s.sha256))
    history={n:distinct_epochs(rows) for n,rows in history.items()}
    assert all(row['epoch']<=cutoff and row['collected_utc_ns']<=cutoff for rows in history.values() for row in rows)
    return dict(case=case,origin_utc_ns=receipt['origin_utc_ns'],cutoff_utc_ns=cutoff,
        past_versions=history,sources=sources,history_window_hours=72,
        candidates=len(elements),genuine_distinct_epochs=True,
        source_sha256=sha(Path(__file__)),latest_elements_sha256=sha(directory/'nominal_elements.json'),
        no_following_TLE_or_GPS=True,archive_access_is_read_only=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    print(json.dumps(export(parser.parse_args().case),allow_nan=False))
