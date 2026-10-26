"""Read-only replay of the unchanged DS25 authority; no geographic evaluation."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024')
RECOVERY = Path('/srv/bulk/leo/research/ds24-movement-policy-r01/recovery')
CASES = tuple(f'DS24-{i:04d}' for i in range(10, 14))
ARMS = ('c0', 'fitted_c')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False, default=encode).encode()).hexdigest()


def encode(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    if not path.resolve().is_relative_to(HERE):
        raise ValueError('output outside validation owner')
    with path.open('x') as stream:
        json.dump(value, stream, default=encode, indent=2, allow_nan=False)
        stream.write('\n')


def imports():
    sys.path[:0] = ['/tmp/algo03-feasible-deps', str(REPO/'src'),
                    str(REPO/'tools'), str(RECOVERY)]
    import recovery
    from evaluate_ds22_merged_tracks import winners
    return recovery, winners


def source_receipt():
    files = {HERE/'PROTOCOL.md', Path(__file__), SOURCE/'protocol.json',
             SOURCE/'source_receipt.json', SOURCE/'engine/ds24_engine.py',
             SOURCE/'engine/run_baseline.py',
             Path('/srv/bulk/leo/research/ds24-ch78-diagnosis-r02/common.py')}
    for module in list(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            path = Path(name).resolve()
            if path.suffix == '.py' and any(path.is_relative_to(p) for p in
                    (REPO, Path('/srv/bulk/leo/research'))):
                files.add(path)
    for case in CASES:
        files.update(SOURCE/case/name for name in ('input_receipt.json',
            'tracking.json', 'prepared.json', 'preparation_receipt.json',
            'observations.json', 'tracks.json', 'bank.npz', 'radio_noise.json',
            'nominal_elements.json', 'receipt.json', 'result.json', 'algo02_result.json'))
        files.add(SOURCE/'family_cavity/position'/f'{case}.json')
        files.update((SOURCE/'causal_prior'/case).glob('*.json'))
        files.update((SOURCE/'causal_prior'/case).glob('*.tle'))
        files.update((SOURCE/'causal_phase_history').glob(case+'*.json'))
    return {str(p): sha(p) for p in sorted(files)}


def native_inventory(case, winners):
    """Reproduce exact public winners and bind full native source support."""
    document = read(SOURCE/case/'tracking.json')
    rows, metadata = winners(document)
    saved = read(SOURCE/case/'observations.json')
    if rows != saved:
        raise ValueError('public original winning row replay differs')
    source = document['source']
    fs = source['sample_rate_hz']
    count = round(source['probe_ms']*0.001*fs)
    receivers = sorted({p['receiver_id'] for p in source['probes']})
    lookup = {o['observation_id']: o for o in rows}
    inventory = []
    for probe in source['probes']:
        start = probe['valid_start_counter']
        oid = 'sha256:'+hashlib.sha256(
            f"{source['session_id']}:{probe['receiver_id']}:{start}".encode()).hexdigest()
        support = dict(recording_id=source['session_id'],
            stream_generation=source['stream_generation'],
            raw_authority_digest=source['raw_recording_authority_digest'],
            native_receiver_id=probe['receiver_id'],
            receiver=receivers.index(probe['receiver_id'])+1,
            channel=probe['channel'], edge=probe['edge'],
            start_counter=start, end_counter=start+count, sample_rate_hz=fs,
            actual_rf_hz=probe['actual_rf_hz'])
        inventory.append(dict(observation_id=oid, support=support,
            time_s=(start-document['clock_anchor']['sample_counter'])/fs+count/(2*fs),
            visit_index=probe['visit_index'], probe_index=probe['probe_index'],
            payload_start_sample=probe['payload_start_sample'], existing_winner=oid in lookup,
            candidates_exposed=len(probe['candidates'])))
        if oid in lookup:
            row=lookup[oid]
            if any(row[k] != support[k] for k in
                   ('native_receiver_id','receiver','channel','actual_rf_hz')):
                raise ValueError('native row mapping changed')
            if row['time_s'] != inventory[-1]['time_s']:
                raise ValueError('native timestamp precision changed')
    if not set(lookup) <= {v['observation_id'] for v in inventory}:
        raise ValueError('unmapped native winner')
    return inventory, metadata


def replay(case, recovery, winners):
    began = time.monotonic()
    d = recovery.context(case)
    inventory, metadata = native_inventory(case, winners)
    memberships = {}
    arms = {}
    for arm in ARMS:
        saved = d['arms'][arm]
        p = recovery.build(d, arm, saved['phase_reference'])
        x = np.asarray(saved['endpoint_east_north_km'])
        calc = p.calculate(x)
        delta = float(calc['negative_twice_elbo']-saved['negative_twice_elbo'])
        if abs(delta)>=1e-3:
            raise ValueError('unchanged objective replay failed')
        ids = [oid for i in p.members for oid in p.scan.tracks[i]['observation_ids']]
        if len(ids)!=len(set(ids)) or len(ids)!=len(p.keep):
            raise ValueError('duplicate or misaligned curved ownership')
        # Existing graph alias lifts and complete-family aliases are separate.
        tracks = []
        lookup = {o['observation_id']: o for o in d['observations']}
        period = recovery.algo.__dict__.get('PERIOD')
        from leo.analysis.research.retained_track_likelihood import PERIOD
        for i, alias in zip(p.members, p.alias, strict=True):
            t = p.scan.tracks[i]
            lifts = [(float(v)-lookup[oid]['measured_cfo_hz'])/PERIOD
                     for v,oid in zip(t['values'], t['observation_ids'], strict=True)]
            if not np.allclose(lifts, np.rint(lifts), rtol=0, atol=1e-8):
                raise ValueError('graph alias lift is not integral')
            tracks.append(dict(component=t['key'], track_index=i, receiver=t['receiver'],
                channel=t['channel'], actual_rf_hz=t['rf_hz'],
                observation_ids=t['observation_ids'], graph_alias_lifts=np.rint(lifts).astype(int),
                complete_family_alias=int(alias)))
        member = recovery.membership(d, arm, saved)
        memberships[arm] = member
        arms[arm] = dict(objective_replay_difference=delta,
            negative_twice_elbo=float(calc['negative_twice_elbo']),
            RMS_hz=float(np.sqrt(np.mean(calc['conditional_residual_hz'][p.keep]**2))),
            observation_ids_in_curved_order=ids, mask=p.keep,
            candidate_rows=p.rows, aliases=p.alias, tracks=tracks,
            all_candidate_norads=d['scan'].norads,
            calibration_supported_slots=p.supported,
            point_noise_hz=p.point_noise, family_powers=d['powers'],
            noise_precision=calc['noise_precision'],
            coefficient_prior_precision=calc['coefficient_prior_precision'],
            phase_reference=p.reference, phase_means=d['means'], phase_model=d['model'],
            curved_observation_ids=member['curved_observation_ids'],
            predictive_observation_ids=member['predictive_observation_ids'],
            postfit_only_observation_ids=member['postfit_only_observation_ids'],
            accepted_observation_ids=member['accepted_observation_ids'],
            likelihood_points=member['likelihood_points'],
            channel_counts={str(ch):sum(lookup[o]['channel']==ch for o in
                member['curved_observation_ids']+member['predictive_observation_ids'])
                for ch in range(1,9)})
    matched = {}
    for key in ('observation_ids_in_curved_order','mask','candidate_rows','aliases',
                'all_candidate_norads','point_noise_hz','family_powers',
                'phase_means','phase_model','curved_observation_ids','predictive_observation_ids'):
        matched[key]=digest(arms['c0'][key])==digest(arms['fitted_c'][key])
    if not all(matched.values()):
        raise ValueError('c ablation changes inputs')
    result = dict(case=case,status='replayed',seconds=time.monotonic()-began,
        authority='ALGO02-v1 + qualified causal signed phase prior + equal-prior family cavity',
        reconstruction_source=str(RECOVERY/'recovery.py'), no_refit=True,
        no_geographic_error_or_GPS_evaluation=True,
        regional_center=[37.906,-122.545], box_width_km=25.,
        original_start_east_north_km=[0.,0.], matched_c_inputs=matched,
        native_inventory=inventory, public_metadata=metadata, arms=arms)
    write(HERE/(case+'_baseline.json'), result)
    return dict(case=case,status='replayed',seconds=result['seconds'],
        native_targets=len(inventory),winners=len(d['observations']),
        arms={a:{k:arms[a][k] for k in ('objective_replay_difference','RMS_hz',
            'likelihood_points','channel_counts')} for a in ARMS})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=CASES)
    parser.add_argument('--seal-only',action='store_true')
    args=parser.parse_args()
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        if os.environ.get(key)!='1':
            raise ValueError('explicit BLAS1 required')
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('580s worker cap')))
    signal.alarm(580)
    recovery,winners=imports()
    receipt=source_receipt()
    if args.seal_only:
        write(HERE/'source_receipt.json',dict(files_sha256=receipt,
            protocol_sha256=sha(HERE/'PROTOCOL.md'),frozen_before_replay=True))
        print(json.dumps(dict(status='sealed',files=len(receipt))))
        return
    frozen=read(HERE/'source_receipt.json')['files_sha256']
    for path,value in frozen.items():
        if sha(path)!=value:
            raise ValueError('frozen source/input changed: '+path)
    if not args.case:
        parser.error('--case required for replay')
    result=replay(args.case,recovery,winners)
    for path,value in frozen.items():
        if sha(path)!=value:
            raise ValueError('frozen source/input changed during replay: '+path)
    result['source_input_hashes_unchanged']=True
    write(HERE/(args.case+'_receipt.json'),result)
    print(json.dumps(result,default=encode))


if __name__=='__main__':
    main()
