"""Whole-probe alternating temporal blocks, independent of candidate values."""
from copy import deepcopy
import hashlib
import json
from leo.cli.shared_fast_position import load_input
from leo.contracts.digests import canonical_digest


def payload(document):return (json.dumps(document,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def digest(value):return 'sha256:'+hashlib.sha256(value).hexdigest()
def key(probe):return tuple(int(probe[k]) for k in ('visit_index','receiver_id','probe_index'))


def group_id(source,probe_key):
    return canonical_digest(dict(capture=source['input_manifest_sha256'],visit=probe_key[0],rx=probe_key[1],probe=probe_key[2]))


def derive_blocks(document,*,block_seconds=20,training_parity=0):
    if isinstance(block_seconds,bool) or not isinstance(block_seconds,int) or block_seconds<=0:
        raise ValueError('Positive integer block duration required')
    if training_parity not in (0,1) or isinstance(training_parity,bool):raise ValueError('Training parity0 or1 required')
    allowed=('source','clock_anchor','delivery_clocks','last_sample_counter')
    metadata={k:deepcopy(document[k]) for k in allowed if k in document};metadata['source']['probes']=[]
    authority_source=load_input(metadata);timing=authority_source.timing
    if timing is None or not timing.qualified:raise ValueError('Qualified timing authority required')
    fs=authority_source.sample_rate_hz;origin=timing.session_start_device_sample_counter
    span=int(document['last_sample_counter'])-origin
    if span<=0:raise ValueError('Positive immutable capture counter span required')
    block_samples=block_seconds*fs;probe_samples=fs*authority_source.probe_ms//1000
    selected=[];train=[];held=[];boundary=[];membership=[];seen=set()
    for probe in document['source']['probes']:
        probe_key=key(probe)
        if probe_key in seen:raise ValueError('Duplicate global raw probe key')
        seen.add(probe_key)
        start=int(probe['valid_start_counter'])-origin+int(probe['probe_start_ms'])*fs//1000
        end=start+probe_samples
        if start<0 or end>span:raise ValueError('Probe escaped capture counter authority')
        first,last=start//block_samples,(end-1)//block_samples
        if first!=last:role='boundary';boundary.append(probe_key)
        elif first%2==training_parity:role='train';train.append(probe_key);selected.append(deepcopy(probe))
        else:role='held';held.append(probe_key)
        membership.append(dict(key=probe_key,global_group_id=group_id(document['source'],probe_key),
            start_sample=start,end_sample=end,start_block=first,end_block=last,role=role))
    if not train or not held:raise ValueError('Nonempty training and held probe groups required')
    derived={k:deepcopy(document[k]) for k in allowed if k in document};derived['source']['probes']=selected
    assert len(train)+len(held)+len(boundary)==len(seen)
    receipt=dict(split_policy='alternating-whole-probe-counter-blocks-v1',block_seconds=block_seconds,
        training_parity=training_parity,origin_utc_ns=timing.first_sample_estimate_utc_ns,
        origin_device_counter=origin,last_sample_counter=int(document['last_sample_counter']),
        sample_rate_hz=fs,capture_seconds=span/fs,original_probe_groups=len(seen),
        training_probe_groups=len(train),held_probe_groups=len(held),boundary_probe_groups=len(boundary),
        training_keys=train,held_keys=held,boundary_keys=boundary,membership=membership,
        training_candidate_measurements=sum(len(p['candidates']) for p in selected),
        preserved_authorities={k:document['source'][k] for k in ('input_manifest_sha256','analysis_manifest_sha256',
            'raw_recording_authority_digest','session_id','stream_generation','radio_id')},
        qualification='Membership uses integer session-relative sample intervals only. Every straddling probe is excluded completely. '
        'Candidate CFO, score, gate, epoch and all model states are unused. Global group IDs retain original capture authority.')
    return derived,receipt


def perturb_excluded(document,receipt):
    other=deepcopy(document);excluded=set(map(tuple,receipt['held_keys']+receipt['boundary_keys']))
    for probe in other['source']['probes']:
        if key(probe) not in excluded:continue
        for candidate in probe['candidates']:
            candidate['fractional_tracking_cfo_hz']+=123456.789
            candidate['fractional_exact_score']+=777.;candidate['fractional_control_score']-=333.
            candidate['fractional_margin']+=1110.
            candidate['passed_fractional_margin_gate']=not candidate['passed_fractional_margin_gate']
    return other
