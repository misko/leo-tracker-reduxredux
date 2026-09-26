"""Independently measure broadband offset on training halves of selected dwells."""
import json
import hashlib
from dataclasses import asdict
from pathlib import Path
import numpy as np
import zstandard
from leo.analysis.starlink.broadband_alignment import estimate_broadband_alignment

HERE = Path(__file__).resolve().parent

def load(index):
    root = Path('/srv/bulk/leo/scanner-adaptive-recordings/scan-fw-32a202b6e55630ec')
    chunk = json.loads((root/'manifest.json').read_text())['manifest']['chunks'][index]
    raw = zstandard.ZstdDecompressor().decompress((root/chunk['relative_path']).read_bytes(),max_output_size=chunk['uncompressed_bytes'])
    assert 'sha256:'+hashlib.sha256(raw).hexdigest()==chunk['uncompressed_sha256']
    a=np.frombuffer(raw,dtype='<i2').reshape(-1,2,2)
    return a[...,0].astype(float)+1j*a[...,1].astype(float)

def main():
    selection=json.loads((HERE/'selection.json').read_text())
    candidates={(int(r['visit_index']),int(r['receiver_id'])):r for r in selection['candidate_rows']}
    rows=[]
    for index in selection['visit_indices']:
        seed=float(candidates[index,1]['tracking_absolute_baseband_cfo_hz'])-float(candidates[index,0]['tracking_absolute_baseband_cfo_hz'])
        result=estimate_broadband_alignment(load(index),1e7,receiver_cfo_seed_hz=seed,cfo_search_half_width_hz=900000)
        m=result.model
        row=dict(visit=index,glrt_difference_hz=seed,broadband_cfo_hz=m.relative_cfo_hz,rate_hz_s=m.relative_cfo_rate_hz_s,reference_sample=m.reference_sample,delay_samples=m.fractional_delay_samples,training=asdict(result.training),held_out=asdict(result.held_out))
        rows.append(row);print(json.dumps(row),flush=True)
        (HERE/'offset-audit.json').write_text(json.dumps(rows,indent=2)+'\n')

if __name__=='__main__':main()
