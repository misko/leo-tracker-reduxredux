"""Freeze RF-only midpoint pilot slots before any raw-window analysis."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024')
CASES = ('DS24-0010', 'DS24-0011')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def choose(probes, receiver, channel, role, midpoint):
    eligible = []
    for probe in probes:
        if (probe['receiver_id'], probe['channel']) != (receiver, channel):
            continue
        candidates = probe['candidates']
        if not candidates:
            continue
        winner = max(candidates, key=lambda c: (c['fractional_margin'], -c['candidate_rank']))
        passed = any(c['passed_fractional_margin_gate'] for c in candidates)
        if ((role == 'passed' and passed) or
                (role == 'failed_near_gate' and not passed and .0125 <= winner['fractional_margin'] < .025)):
            eligible.append((probe, winner))
    if not eligible:
        return None
    return min(eligible, key=lambda v: (abs(v[0]['valid_start_counter'] - midpoint), v[0]['visit_index']))


def nominate():
    slots = []
    sources = {}
    for case in CASES:
        path = SOURCE/case/'tracking.json'
        doc = json.loads(path.read_text())
        source = doc['source']
        probes = source['probes']
        origin = doc['clock_anchor']['sample_counter']
        counters = [p['valid_start_counter'] for p in probes]
        midpoint = (min(counters) + max(counters))/2
        observations = json.loads((SOURCE/case/'observations.json').read_text())
        sources[str(path)] = sha(path)
        sources[str(SOURCE/case/'observations.json')] = sha(SOURCE/case/'observations.json')
        for receiver in (0, 1):
            for channel in (7, 8):
                for role in ('passed', 'failed_near_gate'):
                    request_id = f'{case}-RX{receiver+1}-CH{channel}-{role}'
                    result = choose(probes, receiver, channel, role, midpoint)
                    slot = dict(request_id=request_id, case=case, receiver=receiver+1,
                                native_receiver_id=receiver, channel=channel, role=role)
                    if result is None:
                        slots.append(dict(slot, status='missing', reason='no window satisfying frozen policy'))
                        continue
                    probe, candidate = result
                    matched = [o for o in observations if o['native_receiver_id'] == receiver and
                               o['channel'] == channel and o['measured_cfo_hz'] == candidate['fractional_tracking_cfo_hz'] and
                               o['fractional_margin'] == candidate['fractional_margin']]
                    if role == 'passed' and len(matched) != 1:
                        raise ValueError('passed winner does not uniquely join original observation')
                    slots.append(dict(slot, status='nominated', tracking=dict(path=str(path), sha256=sha(path)),
                        source_input=dict(path=f"/srv/bulk/leo/fast-scan-inputs/{source['session_id']}.json",
                                          sha256=source['input_manifest_sha256']),
                        session_id=source['session_id'], analysis_manifest_sha256=source['analysis_manifest_sha256'],
                        raw_recording_authority_digest=source['raw_recording_authority_digest'],
                        run_id=doc['provenance']['run_id'], sample_rate_hz=source['sample_rate_hz'],
                        original_observation_id=matched[0]['observation_id'] if matched else None,
                        diagnostic_id='sha256:'+hashlib.sha256(json.dumps([case, probe, candidate], sort_keys=True).encode()).hexdigest(),
                        time_s=(probe['valid_start_counter']-origin)/source['sample_rate_hz'],
                        midpoint_time_s=(midpoint-origin)/source['sample_rate_hz'],
                        scan_counter_range=[min(counters), max(counters)],
                        physical_id=f"{case}-visit-{probe['visit_index']:06d}",
                        probe=dict(probe, window_start_counter=probe['valid_start_counter'],
                                   duration_samples=round(source['sample_rate_hz']*source['probe_ms']/1000)),
                        original_candidate=candidate))
    return dict(schema='ch8-pilot-midpoint-panel/v1', slots=slots, source_sha256=sources,
        selection='For each case x native RX0/1 x CH7/8, closest probe start counter to midpoint of min/max processed probe start counters, then visit. One original max-margin passing winner; one no-pass window whose maximum exported margin is in [0.0125,0.025). Candidate ties use lower original rank.',
        target_slots=16, nominated=sum(s['status']=='nominated' for s in slots),
        physical_windows=len({s['physical_id'] for s in slots if s['status']=='nominated'}),
        maximum_physical_read_windows=32, no_GPS_error_rank_orbit_selection=True,
        candidate_rank_used_only_as_original_margin_tie_break=True,
        original_full_window_acquisition_exposure=True, inference_and_admission_unchanged=True,
        nomination_source_sha256=sha(__file__))


if __name__ == '__main__':
    panel = nominate()
    with (HERE/'panel.json').open('x') as f:
        json.dump(panel, f, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps({k: panel[k] for k in ('target_slots', 'nominated', 'physical_windows')}))
    for s in panel['slots']:
        print(s['request_id'], s['status'], s.get('physical_id'),
              s.get('original_candidate', {}).get('candidate_rank'),
              s.get('original_candidate', {}).get('fractional_margin'))
