"""Confirm the frozen age-scale relation on a new date and new satellites."""
import hashlib
import inspect
import json
from pathlib import Path
import sys
import time
import numpy as np
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records,parse_element_sets
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from model import scores

HERE=Path(__file__).resolve().parent;HILL=HERE.parent;PRIOR=HILL/'historical_orbit_forecast'
sys.path.insert(0,str(HILL.parent/'2026_09_29_orbit_revision_support'))
from inventory import epoch_ns
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    started=time.monotonic();cp=HERE/'calibration.json';ip=PRIOR/'inventory.json'
    cal=json.loads(cp.read_text());inv=json.loads(ip.read_text())
    for p,h in cal['sources'].items():assert digest(p)==h,p
    sources={str(p):digest(p) for p in (Path(__file__),HERE/'model.py',HERE/'CONFIRMATION.md',cp,ip,Path(inspect.getfile(epoch_ns)),Path(inspect.getfile(propagate_candidate_states)),Path(inspect.getfile(parse_element_set_records)))}
    excluded=set()
    for i in range(12):
        p=PRIOR/f'center-{i:02d}.json';d=json.loads(p.read_text());sources[str(p)]=digest(p)
        excluded.update(r['norad'] for r in d['rows'])
    day=86400*10**9;center=inv['windows'][-1]['center_utc_ns']+day
    cutoff=inv['cutoff_utc_ns']-day
    reader=TleArchiveReader(Path('/var/lib/leo/tle'))
    refs=[r for r in reader.list_snapshots() if max(r.collected_utc_ns,r.path.stat().st_mtime_ns)<=cutoff]
    occurrences={};cache={}
    def combined(deadline):
        choices=[max((r for r in refs if r.provider==provider and max(r.collected_utc_ns,r.path.stat().st_mtime_ns)<=deadline),key=lambda r:(r.collected_utc_ns,r.digest)) for provider in ('huggingface','space-track')]
        mapping={}
        for ref in choices:
            if ref.digest not in cache:
                text=reader.read(ref);assert hashlib.sha256(text.encode()).hexdigest()==ref.sha256
                parsed=parse_element_set_records(text);cache[ref.digest]={r.satellite_number:r for r in parsed};assert len(cache[ref.digest])==len(parsed)
            sources[str(ref.path)]=digest(ref.path)
            occurrences[str(ref.path)]=dict(provider=ref.provider,request_utc_ns=ref.collected_utc_ns,local_mtime_ns=ref.path.stat().st_mtime_ns)
            for n,r in cache[ref.digest].items():
                key=(epoch_ns(r.first_line),ref.collected_utc_ns,ref.digest)
                if n not in mapping or key>mapping[n][0]:mapping[n]=(key,r)
        return mapping
    old,current,later=[combined(center+d*day) for d in (-1,0,1)]
    common=set(old)&set(current)&set(later)-excluded
    common={n for n in common if current[n][1].name.upper().startswith('STARLINK-') and 'DEB' not in current[n][1].name.upper()}
    sampled=sorted(common,key=lambda n:hashlib.sha256(str(n).encode()).digest())[:256]
    eligible=[n for n in sampled if old[n][0][0]<current[n][0][0]<later[n][0][0]]
    assert not set(eligible)&excluded
    values={}
    for name,table in [('current',current),('later',later)]:
        text=''.join(f'0 {table[n][1].name}\n{table[n][1].first_line}\n{table[n][1].second_line}\n' for n in eligible)
        if not eligible:values[name]=np.zeros((0,3));continue
        catalogue=parse_element_sets(text);assert list(catalogue.satellite_numbers)==eligible
        p,v,valid=propagate_candidate_states(catalogue,range(len(eligible)),center,np.array([-1.,0.,1.]),np.array([0.]))
        np.testing.assert_array_equal(valid,np.arange(len(eligible)))
        values[name]=p[:,0,1]
    ages=np.array([(center-current[n][0][0])/day for n in eligible]);vectors=values['later']-values['current']
    gains=scores(cal['fits']['age']['selected']['parameters'],ages,vectors,True)[0]-scores(cal['fits']['constant']['selected']['parameters'],ages,vectors,False)[0]
    wins=int(np.sum(gains>0));mean=float(np.mean(gains)) if len(gains) else None;median=float(np.median(gains)) if len(gains) else None
    passed=bool(len(gains)>=50 and mean>0 and median>0 and wins>.55*len(gains))
    out=dict(center_utc_ns=center,availability_cutoff_utc_ns=cutoff,previously_exposed_objects=len(excluded),
             unexposed_common_objects=len(common),sampled=len(sampled),excluded_nonadvancing_epochs=len(sampled)-len(eligible),
             eligible_objects=len(eligible),source_wins=wins,mean_gain=mean,median_gain=median,passed=passed,
             rows=[dict(norad=n,age_days=float(a),next_revision_km=v.tolist(),log_score_gain=float(g)) for n,a,v,g in zip(eligible,ages,vectors,gains)],
             archive_occurrences=occurrences,sources=sources,independent_orbit_truth=False,
             causal_position_improvement_established=False,elapsed_s=time.monotonic()-started)
    with (HERE/'confirmation.json').open('x') as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in out.items() if k not in ('rows','archive_occurrences','sources')},indent=2))


if __name__=='__main__':main()
