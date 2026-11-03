"""True temporal-half export, using counter/timing metadata before any CFO."""
from copy import deepcopy
import hashlib
import json
from leo.cli.shared_fast_position import load_input

AUTHORITIES=('source','clock_anchor','delivery_clocks','last_sample_counter')


def payload(document):
    return (json.dumps(document,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def digest(data):return 'sha256:'+hashlib.sha256(data).hexdigest()


def group_key(probe):return tuple(int(probe[k]) for k in ('visit_index','receiver_id','probe_index'))


def temporal_half(document,*,direction='early_to_late'):
    """Retain complete probes on one side of the capture counter midpoint.

    Any straddling probe is excluded from both halves. Candidate dictionaries
    are not inspected for splitting. Original clock and provenance authorities
    remain unchanged; a separate receipt binds this measurement subset.
    """
    if direction not in ('early_to_late','late_to_early'):raise ValueError('Unknown temporal direction')
    metadata={k:deepcopy(document[k]) for k in AUTHORITIES if k in document}
    metadata['source']['probes']=[]
    timing_source=load_input(metadata)
    authority=timing_source.timing
    if authority is None or not authority.qualified:raise ValueError('Qualified timing authority required')
    fs=timing_source.sample_rate_hz;counter=authority.session_start_device_sample_counter
    if 'last_sample_counter' in document:end_counter=int(document['last_sample_counter'])
    else:
        raise ValueError('Immutable terminal sample counter required for the full-capture midpoint')
    span=end_counter-counter
    if span<=0:raise ValueError('Positive capture counter span required')
    probe_count=fs*timing_source.probe_ms//1000
    selected=[];train=[];held=[];boundary=[];seen=set()
    for probe in document['source']['probes']:
        key=group_key(probe)
        if key in seen:raise ValueError('Duplicate raw probe key')
        seen.add(key)
        # Integer differences precede all conversion, including >2**53 counters.
        start=int(probe['valid_start_counter'])-counter+int(probe['probe_start_ms'])*fs//1000
        end=start+probe_count
        if start<0 or end>span:raise ValueError('Probe outside capture counter authority')
        early=2*end<=span;late=2*start>=span
        if not early and not late:boundary.append(key);continue
        use=early if direction=='early_to_late' else late
        (train if use else held).append(key)
        if use:selected.append(deepcopy(probe))
    if not train or not held:raise ValueError('Both complete-probe temporal halves required')
    derived={k:deepcopy(document[k]) for k in AUTHORITIES if k in document}
    derived['source']['probes']=selected
    if set(train)&set(held):raise AssertionError('Probe membership overlap')
    receipt=dict(direction=direction,split_policy='whole-probe-interval-capture-counter-midpoint-v1',
        sample_rate_hz=fs,origin_utc_ns=authority.first_sample_estimate_utc_ns,
        origin_device_counter=counter,last_sample_counter=end_counter,
        capture_seconds=span/fs,cut_s=span/(2*fs),
        original_probe_groups=len(seen),training_probe_groups=len(train),
        held_probe_groups=len(held),boundary_probe_groups=len(boundary),
        training_keys=train,held_keys=held,boundary_keys=boundary,
        training_candidate_measurements=sum(len(p['candidates']) for p in selected),
        preserved_authorities={k:document['source'][k] for k in
            ('input_manifest_sha256','analysis_manifest_sha256','raw_recording_authority_digest',
             'session_id','stream_generation','radio_id')},
        qualification='Capture clock metadata remains full-domain authority. Every candidate measurement from held/straddling probes is removed before inference. No candidate value, GLRT score, bank or position is used to split.')
    return derived,receipt


def perturb_excluded(document,receipt):
    """Leakage check: alter all excluded CFO and detection-score values."""
    changed=deepcopy(document);excluded=set(map(tuple,receipt['held_keys']+receipt['boundary_keys']))
    for probe in changed['source']['probes']:
        if group_key(probe) not in excluded:continue
        for candidate in probe['candidates']:
            candidate['fractional_tracking_cfo_hz']+=123456.789
            candidate['fractional_exact_score']+=777.
            candidate['fractional_control_score']-=333.
            candidate['fractional_margin']+=1110.
            candidate['passed_fractional_margin_gate']=not candidate['passed_fractional_margin_gate']
    return changed
