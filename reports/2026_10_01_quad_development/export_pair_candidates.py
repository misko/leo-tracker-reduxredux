"""Read competing public candidates for the existing DS10 outlier-pair probes."""
import fcntl
import json
from pathlib import Path
import subprocess
import time
from run_window import prepare_window
from check_receiver_curvature import save
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources
from prepare_block import verify_reader,RUNTIME,GOAL
from export_quality_overlay_hypotheses import FIELDS
HERE=Path(__file__).resolve().parent


def validate_groups(selected,candidates):
    lookup={p['candidate_id']:p for p in candidates}
    if len(lookup)!=len(candidates):raise ValueError('duplicate candidate ID')
    groups={p['source_group_id']:[] for p in selected}
    for p in candidates:
        if p['source_group_id'] not in groups:raise ValueError('unexpected source group')
        groups[p['source_group_id']].append(p)
    for p in selected:
        actual=lookup.get(p['candidate_id'])
        if actual is None:raise ValueError('missing selected candidate')
        for key in FIELDS:
            if actual[key]!=p[key]:raise ValueError('selected candidate mismatch: '+key)
    return groups


def main():
    inputs={}
    def read(path):
        d=sealed(path);inputs[str(path)]=digest(path);return d
    inspected=read(HERE/'ds10-pair-inspection-v1/result.json')
    overlay=read(HERE/'quality-overlay-v4/overlay.json');verify_sources(overlay['sources']);verify_sources(overlay['inputs'])
    row=next(r for r in overlay['results'] if r['unit']=='DS10-F001')
    tids={r['track_id'] for r in inspected['tracks']}
    selected=[p for t in row['tracks'] if t['track_id'] in tids for p in t['points']]
    assert len(selected)==80 and len({p['source_group_id'] for p in selected})==80
    obs=json.loads(Path(row['observation_path']).read_text());assert digest(row['observation_path'])==row['observation_sha256']
    inputs[row['observation_path']]=row['observation_sha256']
    code='''
import json,sys
from pathlib import Path
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.application.scanner_trajectory import project_scanner_candidates
store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
try:
 raw=store.load(sys.argv[1]); groups=set(json.loads(sys.argv[2]));fields=json.loads(sys.argv[3])
 points=project_scanner_candidates(raw)
 rows=[{k:getattr(p,k) for k in fields} for p in points if p.source_group_id in groups]
 print(json.dumps(dict(session_id=sys.argv[1],manifest_sha256=raw.input_manifest_sha256,analysis_manifest_sha256=raw.analysis_manifest_sha256,candidates=rows),allow_nan=False))
finally: store.close()
'''
    with (GOAL/'.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        out=HERE/'pair-candidates-v1';out.mkdir(exist_ok=False)
        before=verify_reader();start=time.monotonic()
        call=subprocess.run(['sudo','-n','-u','leo','env','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','MKL_NUM_THREADS=1',
            'timeout','--kill-after=2s','85s',RUNTIME,'-c',code,obs['session_id'],json.dumps([p['source_group_id'] for p in selected]),json.dumps(FIELDS)],
            capture_output=True,text=True,timeout=90)
        save(out/'launch.json',dict(returncode=call.returncode,seconds=time.monotonic()-start,stderr=call.stderr,external_limit_s=90))
        call.check_returncode();data=json.loads(call.stdout)
        for key in ('session_id','manifest_sha256','analysis_manifest_sha256'):assert data[key]==obs[key]
        groups=validate_groups(selected,data['candidates']);after=verify_reader()
        save(out/'candidates.json',dict(**data,reader_before=before,reader_after=after,selected_candidate_ids=[p['candidate_id'] for p in selected],
            group_sizes={k:len(v) for k,v in groups.items()},inputs=inputs,
            sources={str(Path(__file__).resolve()):digest(__file__),str(HERE/'export_quality_overlay_hypotheses.py'):digest(HERE/'export_quality_overlay_hypotheses.py')},
            qualification='Public margin-passing projection only; excluded/subthreshold candidates are unavailable here. No IQ, RF, fit, or original-input changes.'))
        print(dict(groups=len(groups),candidates=len(data['candidates']),minimum=min(map(len,groups.values())),maximum=max(map(len,groups.values()))),flush=True)


if __name__=='__main__':main()
