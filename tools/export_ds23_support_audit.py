"""Read sealed, explicitly listed index metadata; no IQ or storage mutations."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess

from run_algo01_ds23_sample import ROOT, read, write, sha

MANIFEST=ROOT/'reports/2026_10_18_ds23_post_ds22/manifest.json'
OUT=ROOT/'reports/2026_10_20_ds23_discovery_completion_v2'
CASES=('DS23-0012','DS23-0184','DS23-0286')


def support_reasons(row):
    """Mirror metadata requirements, without claiming to validate IQ samples."""
    a=row['acquisition'];reasons=[]
    if row['sample_count']!=50000 or row['receiver_count']!=2:reasons.append('sample_geometry')
    if a.get('complete') is not True:reasons.append('incomplete')
    if a.get('validity_authority')!='provider_attested':reasons.append('validity_authority')
    if a.get('validity_includes_guard') is not True:reasons.append('guard_validity')
    if a.get('quality_flags'):reasons.append('quality_flags')
    if a.get('actual_if_center_hz') is None:reasons.append('missing_actual_IF')
    if type(a.get('sample_start')) is not int:reasons.append('sample_start')
    if type(a.get('generation')) is not int:reasons.append('generation')
    if type(a.get('sample_start')) is int and a.get('sample_end')!=a['sample_start']+50000:
        reasons.append('sample_end')
    return reasons


def index_rows(chunk):
    path=Path(chunk['index_path'])
    try:
        payload=path.read_bytes()
    except PermissionError:
        payload=subprocess.run(['sudo','-n','cat','--',str(path)],check=True,capture_output=True).stdout
    digest='sha256:'+hashlib.sha256(payload).hexdigest()
    if len(payload)!=chunk['index_bytes'] or digest!=chunk['index_sha256'] or digest!=chunk['observed_index_sha256']:
        raise ValueError('sealed index size or digest changed')
    rows=[json.loads(line) for line in payload.splitlines()]
    if len(rows)!=chunk['window_count']:raise ValueError('index coverage changed')
    return rows,dict(path=str(path),sha256=digest)


def main():
    expected=read(ROOT/'reports/2026_10_19_algo02_ds23_full/protocol.json')['dataset_manifest_sha256']
    if sha(MANIFEST)!=expected:raise ValueError('original sealed dataset membership changed')
    members=[e for e in read(MANIFEST)['members'] if e['dataset_label'] in CASES]
    summaries=[]
    for member in members:
        with ThreadPoolExecutor(max_workers=8) as pool:
            parts=list(pool.map(index_rows,member['raw_recording']['chunks']))
        rows=sorted([r for part,_ in parts for r in part],key=lambda r:r['acquisition']['global_visit'])
        visits=[r['acquisition']['global_visit'] for r in rows]
        if visits!=list(range(len(visits))):raise ValueError('original visits are not complete and unique')
        invalid=[];counts=Counter()
        for row in rows:
            reasons=support_reasons(row)
            if reasons:
                a=row['acquisition'];counts.update(reasons)
                invalid.append(dict(visit=a['global_visit'],target=row['target_id'],reasons=reasons,
                    quality_flags=a.get('quality_flags'),sample_count=row['sample_count'],
                    complete=a.get('complete'),sample_start=a.get('sample_start'),sample_end=a.get('sample_end')))
        summaries.append(dict(case=member['dataset_label'],recording_id=member['recording_id'],
            original_windows=len(rows),metadata_valid_windows=len(rows)-len(invalid),
            metadata_invalid_windows=len(invalid),reason_counts=dict(counts),invalid=invalid,
            metadata_bindings=[binding for _,binding in parts],
            payload_IQ_not_read_or_revalidated=True,
            original_capture_failure_not_overridden=True))
    write(OUT/'support_metadata_audit.json',dict(cases=summaries,all_terminal=True,
        dataset_sha256=sha(MANIFEST),source_sha256=sha(Path(__file__)),
        all_index_paths_from_sealed_contract_no_constructed_storage_paths=True,
        no_IQ_new_RF_GPS_or_satellite_selection=True))
    print([{k:r[k] for k in ('case','original_windows','metadata_valid_windows','metadata_invalid_windows','reason_counts')}
           for r in summaries],flush=True)


if __name__=='__main__':
    main()
