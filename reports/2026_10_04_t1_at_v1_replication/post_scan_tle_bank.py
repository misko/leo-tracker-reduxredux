"""Select post-scan orbital elements by epoch only, never by measurement fit.

For each frozen association ID choose the smallest element epoch after scan end
and within 24 h, from archived snapshots collected by 48 h after scan end.
Ties use earliest archive collection, then exact lines. If none exists, retain
the original element and explicitly mark the fallback. No satellite is removed.
This retrospective bank is not available to a real-time causal solution.
"""
import copy
import inspect
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import numpy as np
from leave_one_satellite_out import load,HERE
from subset_positions import enable_research_model,serial
from timing_bound_comparison import digest

OUT=HERE/'post-scan-tle-localization'
INPUTS=Path('/srv/bulk/leo/ds13-18scan-benchmark-20261004/inputs-v2')
SCANS=tuple(f'N{i:02}' for i in range(1,17))
HOUR_NS=3600_000_000_000


def element_records(payload,needed):
    from sgp4.alpha5 import from_alpha5
    records={};lines=payload.splitlines()
    for i,line in enumerate(lines):
        if not line.startswith('1 '):continue
        if i+1>=len(lines) or not lines[i+1].startswith('2 ') or lines[i+1][2:7]!=line[2:7]:
            raise ValueError('Invalid TLE pair')
        number=from_alpha5(line[2:7])
        if number not in needed:continue
        yy=int(line[18:20]);year=1900+yy if yy>=57 else 2000+yy
        epoch=datetime(year,1,1,tzinfo=timezone.utc)+timedelta(days=float(line[20:32])-1.)
        records[number]=dict(number=number,epoch_utc_ns=round(epoch.timestamp()*1e9),
            epoch_utc=epoch.isoformat(),line1=line,line2=lines[i+1])
    return records


def choose_post_scan(candidates,end_ns):
    eligible=[r for r in candidates if end_ns<r['epoch_utc_ns']<=end_ns+24*HOUR_NS
              and end_ns<r['collected_utc_ns']<=end_ns+48*HOUR_NS]
    return min(eligible,key=lambda r:(r['epoch_utc_ns'],r['collected_utc_ns'],r['line1'],r['line2'])) if eligible else None


def frozen_fields_equal(a,b):
    for key in ('times','measured','rf','receiver','channel','group','margin','original_rows','owners',
                'numbers','nodes','initial','fixed_receiver_hz'):
        np.testing.assert_array_equal(getattr(a,key),getattr(b,key))


def build():
    enable_research_model()
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    OUT.mkdir(exist_ok=True)
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    observations={s:json.loads((INPUTS/s/'observations.json').read_text()) for s in SCANS}
    numbers={s:set(map(int,load(s)[0].numbers)) for s in SCANS}
    needed=set().union(*numbers.values())
    lower=min(r['origin_utc_ns'] for r in observations.values())
    upper=max(r['origin_utc_ns'] for r in observations.values())+300_000_000_000+48*HOUR_NS
    snapshots=sorted([s for s in archive.list_snapshots('space-track') if lower<s.collected_utc_ns<=upper],key=lambda s:s.collected_utc_ns)
    pool={n:[] for n in needed};parsed={};sources={}
    for snapshot in snapshots:
        # Cache parsing, but retain each collection timestamp: eligibility is
        # evaluated separately against each scan's end time.
        if snapshot.digest not in parsed:
            parsed[snapshot.digest]=element_records(archive.read(snapshot),needed)
        sources[str(snapshot.path)]=snapshot.digest
        for n,r in parsed[snapshot.digest].items():
            pool[n].append(dict(r,collected_utc_ns=snapshot.collected_utc_ns,source=str(snapshot.path),source_sha256=snapshot.digest))
    summaries=[]
    for scan in SCANS:
        folder=OUT/scan;folder.mkdir(exist_ok=True)
        target=folder/'bank.json';states=folder/'states.npz'
        if target.exists():
            saved=json.loads(target.read_text());assert saved['states_sha256']==digest(states)
            summaries.append(saved['summary']);continue
        data,meta,_=load(scan);obs=observations[scan];origin=obs['origin_utc_ns'];end=origin+300_000_000_000
        old_path=Path(obs['tle']['path']);assert digest(old_path)==obs['tle']['sha256']
        old=element_records(old_path.read_text(),numbers[scan]);selected=[]
        for n in data.numbers:
            n=int(n);choice=choose_post_scan(pool[n],end)
            if choice is None:
                choice=dict(old[n],collected_utc_ns=obs['tle']['collected_utc_ns'],source=str(old_path),source_sha256=obs['tle']['sha256'])
            selected.append(dict(number=n,original=old[n],selected=choice,post_scan=choice['epoch_utc_ns']>end,
                changed=(old[n]['line1'],old[n]['line2'])!=(choice['line1'],choice['line2']),
                original_epoch_relative_hours=(old[n]['epoch_utc_ns']-origin)/HOUR_NS,
                selected_epoch_relative_hours=(choice['epoch_utc_ns']-origin)/HOUR_NS))
        def propagate(which):
            payload='\n'.join(line for r in selected for line in (r[which]['line1'],r[which]['line2']))+'\n'
            catalogue=parse_element_sets(payload)
            assert list(catalogue.satellite_numbers)==data.numbers.tolist()
            position,velocity,valid=propagate_candidate_states(catalogue,list(range(len(data.numbers))),origin,data.nodes,np.array([0.]))
            assert valid.tolist()==list(range(len(data.numbers))),'Invalid state: do not drop any satellite'
            return position[:,0],velocity[:,0]
        oldp,oldv=propagate('original')
        np.testing.assert_allclose(oldp,data.position,atol=1e-8,rtol=0)
        np.testing.assert_allclose(oldv,data.velocity,atol=1e-10,rtol=0)
        position,velocity=propagate('selected')
        with states.open('xb') as f:np.savez_compressed(f,position=position,velocity=velocity,numbers=data.numbers,nodes=data.nodes)
        summary=dict(scan=scan,satellites=len(selected),post_scan=sum(r['post_scan'] for r in selected),
            changed=sum(r['changed'] for r in selected),fallback=sum(not r['post_scan'] for r in selected),
            median_original_epoch_age_h=float(np.median([-r['original_epoch_relative_hours'] for r in selected])),
            median_selected_epoch_after_scan_h=float(np.median([r['selected_epoch_relative_hours'] for r in selected if r['post_scan']])))
        receipt=dict(scope=__doc__,scan=scan,origin_utc_ns=origin,scan_end_utc_ns=end,summary=summary,
            input_sha256=meta['input_sha256'],observations_sha256=digest(INPUTS/scan/'observations.json'),
            implementation_sha256=digest(Path(__file__)),propagation_sha256=digest(Path(inspect.getfile(propagate_candidate_states))),
            states_sha256=digest(states),elements=selected,original_bank_reproduced=True)
        target.write_text(json.dumps(receipt,default=serial,indent=2,allow_nan=False));summaries.append(summary)
        print('POST-SCAN BANK',summary,flush=True)
    (OUT/'selection.json').write_text(json.dumps(dict(scope=__doc__,snapshots_considered=len(snapshots),
        unique_snapshot_sources=sources,summary=summaries),default=serial,indent=2,allow_nan=False))


def load_variant(scan,variant):
    data,meta,previous=load(scan)
    receipt=json.loads((OUT/scan/'bank.json').read_text())
    assert receipt['input_sha256']==meta['input_sha256']
    if variant=='original':return data,meta,previous,receipt
    if variant!='post-scan':raise ValueError('Unknown ephemeris variant')
    source=OUT/scan/'states.npz';assert digest(source)==receipt['states_sha256']
    newer=copy.copy(data)
    with np.load(source) as z:
        np.testing.assert_array_equal(data.numbers,z['numbers']);np.testing.assert_array_equal(data.nodes,z['nodes'])
        newer.position=z['position'].copy();newer.velocity=z['velocity'].copy()
    frozen_fields_equal(data,newer)
    return newer,meta,previous,receipt


if __name__=='__main__':build()
