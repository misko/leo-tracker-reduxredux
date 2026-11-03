"""Metadata-only unsupported-candidate prediction from immutable TRAIN states."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace

import numpy as np

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
CONTROL=REPORTS/'2026_10_17_dsx01_iteration9/point_density_control'
OLD=CONTROL/'inference_results'
BANK=REPORTS/'2026_10_17_dsx01_iteration5/metadata_bank'
TRAIN=REPORTS/'2026_10_17_dsx01_iteration5/blocked_cold/S03-block20-parity0'
CASES=('old_fitted-c','old_zero-c')
PROVISIONAL_ATTEMPT_COUNTS=None
META=('observation_id','times_s','rf_hz','receiver','channel','train_mask','held_mask','boundary_mask')
SELECTED={'selected_number':'number','selected_mean_hz':'prediction_hz',
    'selected_visibility_weight':'visibility_weight','selected_detection_q':'detection_probability',
    'correction_hz':'correction_hz'}


def sha(path):return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def plain(x):
    if isinstance(x,np.ndarray):return x.tolist()
    if isinstance(x,np.generic):return x.item()
    if isinstance(x,dict):return {k:plain(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [plain(v) for v in x]
    return x
def save(path,value):
    with Path(path).open('x') as stream:json.dump(plain(value),stream,indent=2,allow_nan=False);stream.write('\n')
def array_digest(value):
    a=np.asarray(value);h=hashlib.sha256()
    h.update(a.dtype.str.encode());h.update(str(a.shape).encode());h.update(np.ascontiguousarray(a).tobytes())
    return 'sha256:'+h.hexdigest()


def project_metadata(predictions,*,dummy_cfo=0.):
    """No signal-response field is ever requested from the supplied mapping."""
    return SimpleNamespace(window_ids=tuple(map(str,predictions['observation_id'])),
        times_s=np.asarray(predictions['times_s']).copy(),rf_hz=np.asarray(predictions['rf_hz']).copy(),
        receiver=np.asarray(predictions['receiver']).copy(),channel=np.asarray(predictions['channel']).copy(),
        measured_hz=np.full(len(predictions['times_s']),dummy_cfo),margin=np.ones(len(predictions['times_s'])))


def metadata_digest(predictions):
    """Reproduce the sealed metadata bank's report-field projection exactly."""
    rows=[dict(observation_id=str(key),time_s=float(t),actual_rf_hz=float(f),receiver=int(rx)+1,channel=int(ch))
        for key,t,f,rx,ch in zip(predictions['observation_id'],predictions['times_s'],predictions['rf_hz'],
            predictions['receiver'],predictions['channel'],strict=True)]
    return 'sha256:'+hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def complement_indices(eligible,selected):
    eligible,selected=np.asarray(eligible),np.asarray(selected)
    for values in (eligible,selected):
        if values.ndim!=1 or len(np.unique(values))!=len(values) or np.any(values<=0) or np.any(values!=np.floor(values)):
            raise ValueError('Unique positive integer candidate arrays required')
    if not np.isin(selected,eligible).all():raise ValueError('Selected bank is not a subset of metadata bank')
    return np.flatnonzero(~np.isin(eligible,selected))


def validate_authorities(bank_freeze,derivation,terminal):
    if bank_freeze['source_tracking_input_sha256']!=derivation['parent_input_sha256']:
        raise ValueError('Original recording input authority differs')
    if bank_freeze['origin_utc_ns']!=derivation['origin_utc_ns']:raise ValueError('Bank/capture UTC origin differs')
    if bank_freeze['prior']!=terminal['provenance']['prior']:raise ValueError('Regional prior/frame differs')
    for field in ('sha256','provider','collected_utc_ns','payload_sha256'):
        if bank_freeze['causal_tle'][field]!=derivation['causal_tle'][field]:raise ValueError('Causal TLE authority differs: '+field)
    for field,source in [('tle_sha256','sha256'),('tle_collected_utc_ns','collected_utc_ns'),('tle_payload_sha256','payload_sha256')]:
        if terminal['provenance'][field]!=bank_freeze['causal_tle'][source]:raise ValueError('TRAIN terminal TLE differs')
    if terminal['input_sha256']!=derivation['derived_input_sha256']:raise ValueError('TRAIN terminal input differs')


def validate_predictions(predictions,selected,bank_freeze,*,expected_rows=3988):
    if len(predictions['times_s'])!=expected_rows or len(np.unique(predictions['observation_id']))!=expected_rows:
        raise ValueError('Exact unique full metadata rows required')
    if metadata_digest(predictions)!=bank_freeze['metadata_sha256']:raise ValueError('Full metadata/time/RF/RX ordering differs')
    np.testing.assert_array_equal(predictions['number'],selected)
    n,k=expected_rows,len(selected)
    for name,shape in [('prediction_hz',(n,k)),('visibility_weight',(n,k)),('detection_probability',(k,)),('correction_hz',(n,))]:
        value=np.asarray(predictions[name])
        if value.shape!=shape or not np.isfinite(value).all():raise ValueError('Invalid immutable selected prediction '+name)
    if np.any(predictions['visibility_weight']<0) or np.any(predictions['visibility_weight']>1):raise ValueError('Invalid selected visibility')
    q=predictions['detection_probability']
    if np.any(q<=0) or np.any(q>=1) or abs(q.sum()-1.6)>1e-10:raise ValueError('Original selected q budget differs')
    masks=[np.asarray(predictions[name]) for name in ['train_mask','held_mask','boundary_mask']]
    if any(m.shape!=(n,) or m.dtype!=bool for m in masks) or not np.all(sum(m.astype(int) for m in masks)==1):
        raise ValueError('Original role masks must partition every row')


def public_ports():
    from leo.contracts.regional_position import PositionOrbitBank,RegionalPrior
    from leo.analysis.hard60_score import predict_orbits
    from leo.analysis.shared_scan_model import elevation_geometry,horizon_weight
    from leo.analysis import _regional_orbits
    return SimpleNamespace(bank=PositionOrbitBank,prior=RegionalPrior,predict=predict_orbits,elevation=elevation_geometry,horizon=horizon_weight)


def seal_bindings():
    sources=read(CONTROL/'source_freeze.json')['files']
    # Only the required archived TRAIN terminal/derivation metadata are loaded;
    # no input loader, preparation or selected-model replay is invoked.
    paths=[Path(__file__),HERE/'test_prepare.py',HERE/'PROTOCOL.md',BANK/'freeze.json',BANK/'metadata-bank.npz',
        CONTROL/'source_freeze.json',OLD/'outcomes_seal.json',OLD/'predictions_seal.json',TRAIN/'derivation.json',TRAIN/'output/terminal.json']
    for name,field in [('outcomes_seal.json','outcomes'),('predictions_seal.json','predictions')]:
        seal=read(OLD/name)
        if seal['all_two_sealed'] is not True or [r['case'] for r in seal[field]]!=list(CASES):raise ValueError('Exact two-arm old seals required')
        for row in seal[field]:
            if sha(row['path'])!=row['sha256']:raise ValueError('Immutable old endpoint/prediction changed')
            paths.append(Path(row['path']))
    for path in [TRAIN/'derivation.json',TRAIN/'output/terminal.json']:
        if sources[str(path)]!=sha(path):raise ValueError('Old TRAIN provenance source changed')
    public_ports()  # Imports only, no predictor/objective/source preparation.
    paths += [Path(m.__file__).resolve() for name,m in tuple(sys.modules.items())
        if name.startswith('leo.') and getattr(m,'__file__',None) and Path(m.__file__).is_file()]
    return {str(path.resolve()):sha(path) for path in paths}


def freeze():
    save(HERE/'source_freeze.json',dict(files=seal_bindings(),cases=CASES,maximum_seconds=60,
        maximum_orbit_predictors=2,maximum_elevation_calls=2,maximum_horizon_calls=2,
        source_preparations=0,propagations=0,localization_objectives=0,fits=0,held_CFO_reads=0))


def verify():
    for path,value in read(HERE/'source_freeze.json')['files'].items():
        if sha(path)!=value:raise ValueError('Frozen source/input changed: '+path)


def load_inputs():
    """Read-only bank/state/blank-metadata port, never a scientific preparation."""
    verify();ports=public_ports();bank_freeze=read(BANK/'freeze.json');derivation=read(TRAIN/'derivation.json')
    terminal=read(TRAIN/'output/terminal.json');validate_authorities(bank_freeze,derivation,terminal)
    if sha(BANK/'metadata-bank.npz')!=bank_freeze['bank_sha256']:raise ValueError('Metadata bank digest differs')
    with np.load(BANK/'metadata-bank.npz') as data:
        bank=ports.bank(data['numbers'],data['nodes_s'],data['position_km'],data['velocity_km_s'])
    np.testing.assert_array_equal(bank.numbers,bank_freeze['selected_numbers'])
    selected=np.asarray(terminal['candidate_numbers']);indices=complement_indices(bank.numbers,selected)
    if len(bank.numbers)!=845 or len(selected)!=45 or len(indices)!=800:raise ValueError('Exact845/45/800 candidate accounting required')
    outcomes=read(OLD/'outcomes_seal.json');prediction_seal=read(OLD/'predictions_seal.json')
    if prediction_seal['outcomes_seal_sha256']!=sha(OLD/'outcomes_seal.json'):raise ValueError('Old outcome/prediction seals disagree')
    control_source=sha(CONTROL/'source_freeze.json')
    if outcomes['source_freeze_sha256']!=control_source or prediction_seal['source_freeze_sha256']!=control_source:
        raise ValueError('Old endpoint source authority differs')
    arms={}
    for fitrow,predrow in zip(outcomes['outcomes'],prediction_seal['predictions'],strict=True):
        if fitrow['case']!=predrow['case']:raise ValueError('Arm ordering differs')
        fit=read(fitrow['path'])
        with np.load(predrow['path']) as data:predictions={name:data[name].copy() for name in data.files}
        validate_predictions(predictions,selected,bank_freeze)
        if [int(predictions[name].sum()) for name in ['train_mask','held_mask','boundary_mask']]!=[2073,1909,6]:
            raise ValueError('Original2073/1909/6 mask counts differ')
        vector=np.asarray(fit['result']['vector']);nuisance=np.asarray(fit['result']['nuisance'])
        if vector.shape!=(52,) or not np.isfinite(vector).all() or not np.isfinite(nuisance).all():raise ValueError('Complete finite saved TRAIN state required')
        if fitrow['case']=='old_zero-c' and vector[6]!=0:raise ValueError('Saved c0 is not zero')
        arms[fitrow['case']]=dict(vector=vector,nuisance=nuisance,predictions=predictions)
    first=arms[CASES[0]]['predictions']
    for name in META:np.testing.assert_array_equal(first[name],arms[CASES[1]]['predictions'][name])
    return dict(bank=bank.select(indices),prior=ports.prior(**bank_freeze['prior']),metadata=project_metadata(first),
        arms=arms,authority=bank_freeze,selected_number=selected,
        original_shared_score=outcomes['original_shared_score'])


def predict_arm(bank,prior,metadata,arm,ports):
    """One orbital and one elevation call; original selected fields copy only."""
    vector=arm['vector'];old=arm['predictions'];shift=np.full(len(bank.numbers),vector[7])
    mean,_,spatial,slope=ports.predict(bank,metadata,prior,vector[:2],shift,derivatives=True)
    del spatial
    sine,spatial,timing,cells=ports.elevation(bank,metadata,prior,vector[:2],shift)
    del spatial,timing,cells
    weight,_=ports.horizon(sine,1e-5)
    result={name:np.asarray(old[name]).copy() for name in META}
    result.update({new:np.asarray(old[oldname]).copy() for new,oldname in SELECTED.items()})
    result.update(unsupported_number=bank.numbers.copy(),unsupported_mean_hz=mean+old['correction_hz'][:,None],
        unsupported_timing_slope_hz_s=slope,unsupported_visibility_weight=weight,
        common_timing_s=np.array(vector[7]),saved_vector=vector.copy(),saved_nuisance=arm['nuisance'].copy(),
        sigma_hz=np.array(125.),visibility_width=np.array(1e-5))
    for new,oldname in SELECTED.items():
        if array_digest(result[new])!=array_digest(old[oldname]):raise ValueError('Immutable selected array changed')
    for name in ['unsupported_mean_hz','unsupported_timing_slope_hz_s','unsupported_visibility_weight']:
        if result[name].shape!=(len(metadata.times_s),len(bank.numbers)) or not np.isfinite(result[name]).all():
            raise ValueError('Invalid new unsupported prediction '+name)
    return result


def run():
    global PROVISIONAL_ATTEMPT_COUNTS
    begun=time.monotonic();verify();inputs=load_inputs();ports=public_ports();records=[]
    ledger=dict(orbit_predictors=0,elevation_calls=0,horizon_calls=0,source_preparations=0,
        propagations=0,localization_objectives=0,fits=0,held_CFO_reads=0,station_reference_reads=0)
    PROVISIONAL_ATTEMPT_COUNTS=ledger
    for key in CASES:
        if time.monotonic()-begun>=58:raise TimeoutError('Whole preparation bound before arm')
        # Exactly one macro call of each type is declared inside predict_arm.
        ledger['orbit_predictors']+=1;ledger['elevation_calls']+=1;ledger['horizon_calls']+=1
        output=predict_arm(inputs['bank'],inputs['prior'],inputs['metadata'],inputs['arms'][key],ports)
        path=HERE/f'prepared_{key}.npz'
        with path.open('xb') as stream:np.savez_compressed(stream,**output)
        records.append(dict(case=key,path=str(path),sha256=sha(path),
            array_sha256={name:array_digest(value) for name,value in output.items()}))
        del output
        verify()
    save(HERE/'predictions_seal.json',dict(all_two_sealed=True,predictions=records,ledger=ledger,
        source_freeze_sha256=sha(HERE/'source_freeze.json'),old_outcomes_seal_sha256=sha(OLD/'outcomes_seal.json'),
        old_predictions_seal_sha256=sha(OLD/'predictions_seal.json'),metadata_sha256=inputs['authority']['metadata_sha256'],
        original_shared_score=inputs['original_shared_score'],observations=3988,selected=45,unsupported=800,
        elapsed_seconds=time.monotonic()-begun,held_CFO_scored=False,
        qualification='Frozen TRAIN-state metadata-only linear-timing inputs; no Gaussian-marginal or recovery claim'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['freeze','run']);args=parser.parse_args()
    if args.action=='freeze':freeze()
    else:
        try:run()
        except Exception as error:
            save(HERE/'failure.json',dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc(),automatic_retry=False,
                provisional_attempt_counts=PROVISIONAL_ATTEMPT_COUNTS,
                count_qualification='Allowances debited before each arm; on failure these are not completed-call counts and may include calls not entered'))
            raise
