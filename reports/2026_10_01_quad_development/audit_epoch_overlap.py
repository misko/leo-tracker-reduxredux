"""Count repeated fitted satellite identities before proposing timing sharing."""
import argparse
from collections import defaultdict, Counter
import json
from pathlib import Path
from run_window import prepare_window
from regression_batch import digest

HERE=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser();parser.add_argument('block');args=parser.parse_args()
    directory=HERE/'independent-v2'/args.block
    audit=directory/'evaluation.json';assert digest(audit)==audit.with_suffix('.sha256').read_text().strip()
    audit_doc=json.loads(audit.read_text());name=args.block+'-Q'
    row=next(r for r in audit_doc['rows'] if r['unit']==name);assert row['accepted']
    path=directory/(name+'.json');assert digest(path)==row['receipt_sha256']
    receipt=json.loads(path.read_text());_,scans,_,_,_=prepare_window(name)
    assigned=receipt['best']['associations'];offset=0;groups=defaultdict(set);clutter=0
    for scan,_,ports in scans:
        metadata=json.loads((HERE/'prepared'/scan.unit_id/'orbits.json').read_text())
        for index in assigned[offset:offset+len(ports)]:
            if index==len(scan.bank.norad_ids):clutter+=1
            else:groups[(metadata['tle']['sha256'],int(scan.bank.norad_ids[index]))].add(scan.unit_id)
        offset+=len(ports)
    assert offset==len(assigned)
    histogram=dict(sorted(Counter(len(s) for s in groups.values()).items()))
    result=dict(block=args.block,active_satellite_snapshot_groups=len(groups),
        repeated_groups=sum(len(s)>1 for s in groups.values()),scan_count_histogram=histogram,
        clutter_tracks=clutter,groups=[dict(snapshot=k[0],norad=k[1],scans=sorted(v)) for k,v in sorted(groups.items())],
        audit_sha256=digest(audit),receipt_sha256=digest(path),source_sha256=digest(__file__),
        qualification='Overlap of fitted identities in an accepted quad, not an independent satellite truth label. No geographic coordinates read. Zero repeated active groups means shared-epoch coupling cannot change the local fixed-signal-label objective, though a cold search may choose different labels and visibility-dependent background may differ.')
    out=directory/'epoch-overlap.json'
    with out.open('x') as stream:json.dump(result,stream,indent=2)
    out.with_suffix('.sha256').write_text(digest(out)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='groups'},indent=2))


if __name__=='__main__':main()
