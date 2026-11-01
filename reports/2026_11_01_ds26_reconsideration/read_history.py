"""Read-only archive export; stdout only, no inference or artifact writes."""
import json,sys
from pathlib import Path
from sgp4.api import Satrec
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records

def collect(cutoff,latest):
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));chosen={}
    snapshots=[s for s in archive.list_snapshots('space-track') if cutoff-int(72*3.6e12)<=s.collected_utc_ns<=cutoff]
    for s in snapshots:
        for r in parse_element_set_records(archive.read(s)):
            n=str(r.satellite_number)
            if n not in latest:continue
            lines=[x for x in r.text.splitlines() if x.startswith(('1 ','2 '))]
            if len(lines)!=2:continue
            sat=Satrec.twoline2rv(*lines);epoch=int(round((sat.jdsatepoch-2440587.5+sat.jdsatepochF)*86400e9))
            # Match the repository's genuine-prior repair: TLE formatting
            # round-trip differences below one second are not new history.
            if latest[n]-epoch<1_000_000_000:continue
            if n in chosen and chosen[n]['epoch_utc_ns']>=epoch:continue
            chosen[n]=dict(lines=lines,epoch_utc_ns=epoch,collected_utc_ns=s.collected_utc_ns,digest=s.digest)
    return dict(chosen=chosen,snapshot_count=len(snapshots))

if __name__=='__main__':
    request=json.load(sys.stdin);print(json.dumps(collect(request['cutoff'],request['latest'])))
