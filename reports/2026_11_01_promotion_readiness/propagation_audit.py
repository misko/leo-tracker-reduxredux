"""Read-only causal catalogue propagation audit on the exact discovery grid.

No receiver/GPS data, candidate RF scores, or mutable archive access is used.
This defines a proposed research eligibility receipt, not production policy.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import time

import numpy as np
import sgp4
from sgp4.api import Satrec, SatrecArray, SGP4_ERRORS
from leo.sky.frames import julian_day_from_utc_ns

OUT=Path(__file__).resolve().parent
REPO=OUT.parents[1]
SEALED=REPO/'reports/2026_11_01_reconsideration_population'
INPUT=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_01_ds26_ds27_causal_variants/inputs')
GRID=np.arange(-40.,341.,1.)
# Error 5 is explicitly obsolete in sgp4 2.27; it is not an eligibility rule.
EXPLICIT_MODEL_INVALID_CODES=frozenset({1,2,3,4,6})


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def classify(errors,positions,velocities):
    """Exclude only one documented model-invalid code at every grid knot."""
    errors=np.asarray(errors);finite=np.isfinite(positions).all(axis=1)&np.isfinite(velocities).all(axis=1)
    if errors.ndim!=1 or len(errors)!=len(finite) or len(errors)==0:raise ValueError('nonempty matching propagation grid required')
    unique=np.unique(errors)
    if np.all(errors==0):return 'eligible' if finite.all() else 'block_nonfinite_without_error'
    if np.any(errors==0):return 'block_partial_grid_failure'
    if len(unique)==1 and int(unique[0]) in EXPLICIT_MODEL_INVALID_CODES:return 'exclude_consistent_model_invalid_all_grid'
    return 'block_unknown_or_inconsistent_all_grid_failure'


def classification_receipt(errors,positions,velocities):
    """Reusable status/count receipt; classify() supplies the narrow status."""
    errors=np.asarray(errors);codes,counts=np.unique(errors,return_counts=True)
    return dict(status=classify(errors,positions,velocities),knots=int(len(errors)),
        error_counts={str(int(c)):int(n) for c,n in zip(codes,counts)},zero_error_knots=int(sum(errors==0)),
        finite_position_knots=int(np.isfinite(positions).all(axis=1).sum()),
        finite_velocity_knots=int(np.isfinite(velocities).all(axis=1).sum()))


def audit(case,catalogue_path,input_path,key):
    catalogue=json.loads(catalogue_path.read_text());records=catalogue[key]
    receipt=json.loads(input_path.read_text())['scan_receipt'];origin=receipt['origin_utc_ns'];cutoff=receipt['cutoff_utc_ns']
    nums=sorted(map(int,records));sats=[Satrec.twoline2rv(*records[str(n)]['lines']) for n in nums]
    utc=origin+np.rint(GRID*1e9).astype(np.int64);jd,fr=julian_day_from_utc_ns(utc)
    errors,positions,velocities=SatrecArray(sats).sgp4(jd,fr)
    inherited_usable=np.asarray(errors==0).all(axis=1);failures=[];counts={};causal_failures=[]
    for k,(n,sat) in enumerate(zip(nums,sats)):
        record=records[str(n)];epoch=record['element_epoch_utc_ns'];collection=record['collected_utc_ns']
        parsed_epoch=int(round(((sat.jdsatepoch-2440587.5)+sat.jdsatepochF)*86400e9))
        if not(0<=cutoff-epoch<=72*3.6e12 and collection<=cutoff and abs(parsed_epoch-epoch)<=1_000_000):
            causal_failures.append(dict(norad=n,ledger_epoch_utc_ns=epoch,parsed_epoch_utc_ns=parsed_epoch,collected_utc_ns=collection))
        verdict=classify(errors[k],positions[k],velocities[k]);counts[verdict]=counts.get(verdict,0)+1
        if verdict=='eligible':continue
        codes,number=np.unique(errors[k],return_counts=True);radii=np.linalg.norm(positions[k],axis=1);finite=radii[np.isfinite(radii)]
        failures.append(dict(norad=n,name=record.get('name'),classification=verdict,
            error_counts={str(int(c)):int(v) for c,v in zip(codes,number)},error_messages={str(int(c)):SGP4_ERRORS.get(int(c),'unknown error code') for c in codes},
            error_code_by_grid=errors[k].astype(int).tolist(),zero_error_knots=int(sum(errors[k]==0)),
            finite_position_knots=int(np.isfinite(positions[k]).all(axis=1).sum()),finite_velocity_knots=int(np.isfinite(velocities[k]).all(axis=1).sum()),
            finite_radius_min_km=float(finite.min()) if len(finite) else None,finite_radius_max_km=float(finite.max()) if len(finite) else None,
            radius_reason=None if len(finite) else 'SGP4 returns no finite position on this grid; a radius cannot be inferred',
            element_epoch_utc_ns=epoch,parsed_epoch_utc_ns=parsed_epoch,collected_utc_ns=collection,
            element_age_hours=(cutoff-epoch)/3.6e12,collection_age_hours=(cutoff-collection)/3.6e12,
            provider=record.get('provider'),snapshot_digest=record.get('snapshot_digest'),
            element_lines=record['lines'],element_sha256=hashlib.sha256(('\n'.join(record['lines'])+'\n').encode()).hexdigest()))
    return dict(case=case,catalogue_path=str(catalogue_path),catalogue_sha256=sha(catalogue_path),
        input_path=str(input_path),input_sha256=sha(input_path),origin_utc_ns=origin,cutoff_utc_ns=cutoff,
        candidate_count=len(nums),inherited_bank_failed_ids=np.asarray(nums)[~inherited_usable].tolist(),
        inherited_usable_count=int(sum(inherited_usable)),classification_counts=counts,
        eligible_ids_sha256=hashlib.sha256(json.dumps([n for k,n in enumerate(nums) if inherited_usable[k]],separators=(',',':')).encode()).hexdigest(),
        nominal_causality_verified=not causal_failures,causal_failures=causal_failures,failures=failures,
        partial_or_unknown_blocks=[r['norad'] for r in failures if r['classification'].startswith('block')])


def main():
    began=time.monotonic();sources=[]
    # Requested development cases are an audit roster, never an identity rule.
    for case in ['DS26-0034','DS26-0044','DS26-0066','DS26-0251']:
        sources.append((case,SEALED/'ledgers'/case/'tle-ledger.json',INPUT/(case+'.json'),'causal'))
    for path in sorted((OUT/'fresh/catalogues').glob('FRSH-*.json')):
        sources.append((path.stem,path,OUT/'fresh/inputs'/path.name,'elements'))
    results=[]
    for args in sources:
        result=audit(*args);results.append(result)
        print(result['case'],result['candidate_count'],[(r['norad'],r['error_counts'],r['classification']) for r in result['failures']],flush=True)
    output=dict(revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),code_sha256=sha(__file__),
        created_utc_ns=time.time_ns(),sgp4_version=sgp4.__version__,documented_error_codes=SGP4_ERRORS,
        grid=dict(start_s=-40,end_s=340,step_s=1,knots=len(GRID),relative_to='scan_receipt.origin_utc_ns'),
        equivalence='same UTC nanosecond rounding, julian_day_from_utc_ns, SatrecArray SGP4 and all(error==0) mask as bank_for/ecef_states/propagate_grid; radii use returned TEME vectors',
        policy='eligible only when every knot has error=0 and finite position/velocity; exclude only a single documented model-invalid code from {1,2,3,4,6} at ALL knots; partial failures, nonfinite-without-error, mixed/unknown errors BLOCK the catalogue rather than silently disappearing',
        interpretation='A model-invalid TLE propagation is not independent evidence of physical satellite decay. Error 1 means propagated mean eccentricity outside 0..1; code6 reports model-decayed radius. No radius is invented from nonfinite states.',
        results=results,seconds=time.monotonic()-began,production_changed=False)
    (OUT/'propagation_audit.json').write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
