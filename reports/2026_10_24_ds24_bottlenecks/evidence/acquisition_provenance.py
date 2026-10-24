"""Read one representative sealed acquisition chain; output metadata only."""
import hashlib
import json
from pathlib import Path
import numpy as np
from leo.contracts.digests import canonical_digest
from leo.contracts.fast_scan_native import parse_fast_result

ROOT=Path('/srv/bulk/leo/research/ds25-20261024')
case='DS24-0101'
tracking=json.loads((ROOT/case/'tracking.json').read_text())
source=tracking['source'];run=tracking['provenance']['run_id']
folder=Path('/srv/bulk/leo/analysis')/source['session_id']/run
manifest=json.loads((folder/'manifest.json').read_text())
segments=[];digests=[];residual=[];acquired=[];output=[]
for product in manifest['products']:
    if product['kind']!='fast-scan.glrt':continue
    path=Path('/srv/bulk/leo')/product['logical_uri'].removeprefix('bulk://')
    raw=path.read_bytes();digest='sha256:'+hashlib.sha256(raw).hexdigest()
    assert digest==product['digest']
    document=json.loads(raw);segments.append(parse_fast_result(document).model_dump(mode='json'))
    digests.append(digest)
    for window in document['windows']:
        for receiver in window['receivers']:
            for candidate in receiver['candidates']:
                if candidate['fractional_residual_cfo_hz'] is not None:
                    residual.append(candidate['fractional_residual_cfo_hz'])
                    acquired.append(candidate['acquired_cfo_hz']);output.append(candidate['fractional_tracking_cfo_hz'])
aggregate=canonical_digest(segments)
assert aggregate==source['analysis_manifest_sha256']
step=1/(512*4.4e-6)
rr=np.array(residual);aa=np.array(acquired);oo=np.array(output)
sample=json.loads((ROOT/'sample.json').read_text())
member=next(m for m in sample['selected'] if m['dataset_label']==case)
raw_manifest_path=Path(member['raw_manifest_receipts'][0]['path'])
raw=json.loads(raw_manifest_path.read_text())
result=dict(case=case,analysis_products=len(segments),analysis_product_hashes_verified=True,
    aggregate_analysis_digest=aggregate,aggregate_matches_frozen_tracking_input=True,
    pipeline_release_id=manifest['pipeline_release_id'],native_policy=segments[0]['policy'],
    raw_manifest_path=str(raw_manifest_path),raw_sample_rate_hz=raw['sample_rate_hz'],raw_window_ms=raw['window_ms'],
    raw_configuration=raw['configuration'],
    fractional_candidates=len(rr),fractional_residual_grid_hz=step,
    residual_max_distance_from_integer_bins=float(np.max(abs(rr/step-np.rint(rr/step)))),
    fractional_CFO_minus_acquired_minus_residual_max_hz=float(np.max(abs(oo-aa-rr))),
    fractional_candidates_zero_residual=int((rr==0).sum()),
    note='Candidate statistics include all bracketed fractional candidates, not only winning retained observations. No raw IQ read. Source/API contracts establish estimator semantics, not a calibrated physical CFO uncertainty.')
print(json.dumps(result,indent=2))
