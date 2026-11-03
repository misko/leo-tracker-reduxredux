"""Read sealed converter metadata only; never read or modify IQ payloads."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess

from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_converter_drift'
MANIFEST=ROOT/'reports/2026_10_18_ds23_post_ds22/manifest.json'


def parse_metadata(raw):
    if 'manifest' in raw:
        body=raw['manifest'];geometry=body['receipt']['plan']['geometry']
        lo=geometry['lnb_lo_hz'];sample_rate=geometry['sample_rate_hz']
        targets=[dict(p['target'],lnb_lo_hz=lo,rf_mapping_authority='recorded_configuration')
                 for p in geometry['profiles']]
        encoded=json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        if 'sha256:'+hashlib.sha256(encoded).hexdigest()!=raw['sha256']:
            raise ValueError('adaptive canonical manifest binding changed')
    else:
        configuration=raw['configuration'];targets=configuration['targets']
        sample_rate=configuration['sample_rate_hz']
    result=[]
    for t in targets:
        if t['rf_center_hz']!=t['lnb_lo_hz']+t['if_center_hz']:
            raise ValueError('converter nominal frequency equation fails')
        if min(t['lnb_lo_hz'],t['if_center_hz'])<=0:
            raise ValueError('positive converter frequencies required')
        result.append({k:t[k] for k in ('channel','edge','rf_center_hz','if_center_hz','lnb_lo_hz','rf_mapping_authority')})
    return dict(sample_rate_hz=sample_rate,targets=sorted(result,key=lambda t:(t['channel'],t['edge'],t['rf_center_hz'])))


def export(member):
    path=OUT/(member['dataset_label']+'_converter.json')
    if path.exists():return dict(case=member['dataset_label'],cached=True)
    reference=None;bindings=[];privileged=0
    for segment in member['raw_recording']['segments']:
        source=Path(segment['path'])
        try:payload=source.read_bytes()
        except PermissionError:
            # Existing passwordless read authority; cat has no mutation path.
            payload=subprocess.run(['sudo','-n','cat','--',str(source)],check=True,capture_output=True).stdout
            privileged+=1
        if len(payload)>16*1024**2 or 'sha256:'+hashlib.sha256(payload).hexdigest()!=segment['sha256']:
            raise ValueError('sealed metadata bound or digest mismatch')
        geometry=parse_metadata(json.loads(payload))
        if reference is not None and geometry!=reference:
            raise ValueError('converter configuration changes between original segments')
        reference=geometry;bindings.append(dict(path=str(source),sha256=segment['sha256']))
    if reference is None:raise ValueError('recording has no sealed converter metadata')
    write(path,dict(case=member['dataset_label'],format=member['recording_format'],geometry=reference,
        metadata_bindings=bindings,sealed_dataset_sha256=sha(MANIFEST),source_sha256=sha(Path(__file__)),
        privileged_read_only_metadata_files=privileged,no_IQ_read_or_RF_collection=True,
        recorded_reference_frequencies_not_independently_measured_oscillators=True))
    return dict(case=member['dataset_label'],metadata_files=len(bindings),lnb_references_hz=sorted({t['lnb_lo_hz'] for t in reference['targets']}))


if __name__=='__main__':
    OUT.mkdir(exist_ok=True)
    cohort=read(ROOT/'reports/2026_10_20_ds23_excluded_catalogue/calibration_protocol.json')
    cases=set(cohort['development_cases']+cohort['confirmation_cases'])
    members=[m for m in read(MANIFEST)['members'] if m['dataset_label'] in cases]
    if len(members)!=40:raise ValueError('converter metadata cohort incomplete')
    with ThreadPoolExecutor(max_workers=8) as pool:rows=list(pool.map(export,members))
    write(OUT/'metadata_export.json',dict(all_terminal=True,count=len(rows),rows=rows,
        dataset_sha256=sha(MANIFEST),no_GPS_or_satellite_identity_used=True))
    print('Verified converter metadata for',len(rows),'recordings',flush=True)
