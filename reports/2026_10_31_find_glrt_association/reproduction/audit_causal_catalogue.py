"""Read-only as-of archive audit for finalists discovered by catalogue search."""
import argparse
import json
from pathlib import Path
from sgp4.api import Satrec
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records


def main(out):
    targets=json.loads((out/'targets.json').read_text());scans={};wanted=set()
    for row in targets:
        result=json.loads((out/'cases'/row['case']/(row['fragment_id']+'.json')).read_text())
        receipt=json.loads((out/'cases'/row['case']/'receipt.json').read_text())['scan_receipt']
        s=scans.setdefault(row['case'],dict(cutoff=receipt['cutoff_utc_ns'],numbers=set()))
        s['numbers'].update(result['finalists']);wanted.update(result['finalists'])
    reader=TleArchiveReader(Path('/var/lib/leo/tle'))
    lo=min(s['cutoff'] for s in scans.values())-int(14*86400e9);hi=max(s['cutoff'] for s in scans.values())
    snapshots=[s for s in reader.list_snapshots('space-track') if lo<=s.collected_utc_ns<=hi]
    records=[]
    for snap in snapshots:
        for r in parse_element_set_records(reader.read(snap)):
            if r.satellite_number not in wanted:continue
            lines=[line for line in r.text.splitlines() if line.startswith(('1 ','2 '))]
            sat=Satrec.twoline2rv(*lines);epoch=round((sat.jdsatepoch-2440587.5)*86400e9+sat.jdsatepochF*86400e9)
            name=next((line for line in r.text.splitlines() if not line.startswith(('1 ','2 '))), '')
            records.append(dict(norad=r.satellite_number,name=name,lines=lines,epoch_utc_ns=epoch,collected_utc_ns=snap.collected_utc_ns,snapshot_digest=snap.digest))
    output={}
    for case,s in scans.items():
        rows={}
        for n in sorted(s['numbers']):
            eligible=[r for r in records if r['norad']==n and s['cutoff']-int(14*86400e9)<=r['collected_utc_ns']<=s['cutoff'] and r['epoch_utc_ns']<=s['cutoff']]
            latest=max(eligible,key=lambda r:(r['epoch_utc_ns'],r['collected_utc_ns'])) if eligible else None
            recent=[r for r in eligible if min(r['collected_utc_ns'],r['epoch_utc_ns'])>=s['cutoff']-int(48*3600e9)]
            selected=max(recent,key=lambda r:(r['epoch_utc_ns'],r['collected_utc_ns'])) if recent else None
            rows[str(n)]=dict(latest_past_within_14d_archive=latest,eligible_48h=selected)
        output[case]=rows
    print(json.dumps(dict(snapshots=len(snapshots),scans=output),allow_nan=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);main(p.parse_args().output)
