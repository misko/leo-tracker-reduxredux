"""Freeze N01-N64 original-window numerical ports via read-only public readers."""
import concurrent.futures as futures
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.application.regional_position_inputs import prepare_position_windows
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.sky.propagation import parse_element_sets
from leo.analysis.regional_position_bank import build_regional_bank
from leo.contracts.regional_position import RegionalPrior, POSITION_SCORES
from leo.contracts.digests import canonical_digest

HERE=Path(__file__).resolve().parent
COHORT=HERE.parent/'2026_10_05_receiver_sky_82/cohort.json'

def digest(path):return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path,value):
    temporary=Path(path).with_suffix('.tmp')
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');temporary.replace(path)

def prepare(scan):
    label=scan['label'];target=HERE/'inputs'/label;target.mkdir(parents=True,exist_ok=True)
    completed=target/'inputs.json'
    if completed.exists():
        saved=json.loads(completed.read_text())
        assert saved['cohort_sha256']==digest(COHORT)
        assert saved['input_manifest_sha256']==scan['manifest_sha256']
        assert saved['arrays_sha256']==digest(target/'arrays.npz')
        return dict(label=label,status='ready',observations=saved['observation_count'],reused=True)
    started=time.monotonic();store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:
        source=store.load(scan['session_id'])
        assert source.input_manifest_sha256==scan['manifest_sha256']
        prepared=prepare_position_windows(source)
        archive=TleArchiveReader(Path('/var/lib/leo/tle'))
        ref=archive.select_latest_before(prepared.start_utc_ns)
        payload,_=exclude_labelled_starlink_debris(archive.read(ref));cat=parse_element_sets(payload)
        indices=np.asarray([i for i,name in enumerate(cat.names) if name.upper().startswith('STARLINK')])
        prior=RegionalPrior()
        bank,receipt=build_regional_bank(cat,indices,prepared.start_utc_ns,prepared.observations,prior,maximum_seconds=60.)
        arrays={'obs_'+n:np.asarray(getattr(prepared.observations,n)) for n in
                ['window_ids','times_s','measured_hz','rf_hz','receiver','channel','margin']}
        arrays.update({'bank_'+n:getattr(bank,n) for n in ['numbers','nodes_s','position_km','velocity_km_s']})
        path=target/'arrays.npz'
        with path.open('xb') as stream:np.savez_compressed(stream,**arrays)
        result=dict(label=label,session_id=scan['session_id'],sample_rate_hz=scan['sample_rate_hz'],
                    capture_start_ns=scan['capture_start_ns'],capture_local=scan['capture_local'],
                    time_block=scan['time_block'],cohort_sha256=digest(COHORT),
                    input_manifest_sha256=source.input_manifest_sha256,analysis_manifest_sha256=source.analysis_manifest_sha256,
                    observation_evidence_sha256=prepared.evidence_sha256,start_utc_ns=prepared.start_utc_ns,
                    observation_count=len(prepared.observations.window_ids),bank_count=len(bank.numbers),
                    bootstrap_tracks=prepared.bootstrap_tracks,prior=asdict(prior),score=asdict(POSITION_SCORES['V16']),
                    arrays_sha256=digest(path),tle_sha256=ref.digest,tle_collected_utc_ns=ref.collected_utc_ns,
                    retained_numbers=bank.numbers.tolist(),elapsed_s=time.monotonic()-started)
        write(completed,result)
        out=dict(label=label,status='ready',observations=result['observation_count'],bank=result['bank_count'],elapsed_s=result['elapsed_s'])
    except Exception as error:
        out=dict(label=label,status='failed',error=type(error).__name__+': '+str(error),elapsed_s=time.monotonic()-started)
        write(target/'failure.json',out)
    finally:store.close()
    print(json.dumps(out),flush=True)
    return out

def main():
    source=json.loads(COHORT.read_text())
    labels=[f'N{i:02d}' for i in range(1,65)]
    scans=[next(s for s in source['scans'] if s['label']==label) for label in labels]
    selected=HERE/'cohort.json'
    if not selected.exists():write(selected,dict(labels=labels,source=str(COHORT),source_sha256=digest(COHORT),scans=scans))
    else:assert json.loads(selected.read_text())['labels']==labels
    old=json.loads((HERE.parent/'2026_10_04_ds13_18_scan_benchmark/cohort-v2.json').read_text())
    write(HERE/'evaluation.json',dict(reference_latitude_deg=old['known_roof_lat_lon'][0],
                                    reference_longitude_deg=old['known_roof_lat_lon'][1],usage='evaluation after fitting and score selection'))
    results=[]
    with futures.ProcessPoolExecutor(max_workers=4) as pool:
        jobs=[pool.submit(prepare,s) for s in scans]
        for job in futures.as_completed(jobs):
            results.append(job.result());write(HERE/'preparation.json',dict(completed=len(results),requested=64,rows=results))
    print('PREPARATION_COMPLETE',len(results),sum(r['status']=='ready' for r in results),flush=True)

if __name__=='__main__':main()
