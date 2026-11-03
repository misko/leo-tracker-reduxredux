"""Reference-blind fitted offset coherence; not receiver oscillator calibration."""
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from candidate_cached_joint import LIGHT_KM_S, CandidateJointObjective
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent
PERIOD = 1/4.4e-6


def wrap(value):
    return (value+PERIOD/2) % PERIOD-PERIOD/2


def main():
    started = time.monotonic()
    freeze = HERE/'vectorized-proposals-v1/sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    frozen = json.loads(freeze.read_text())
    sources = frozen['source_sha256']
    sources[str(Path(__file__))] = digest(__file__)
    verify_sources(sources)
    units = [u for u, arm in frozen['pairs'] if arm == 'candidate']
    rows, groups = [], []
    for unit in units:
        path = freeze.parent/(unit+'-candidate.json')
        assert digest(path) == path.with_suffix('.sha256').read_text().strip()
        parent = json.loads(path.read_text())
        assert parent['converged']
        state = np.asarray(parent['full_state'])
        model = CandidateJointObjective(unit, state=state, assignments=parent['assignments'])
        value = model.evaluate(model.initial, gradient=False)[0]
        assert abs(value-parent['final_objective']) < 1e-7
        receiver = model.receiver(state[:2])
        factor = (model.base.scan.config.doppler_sign
                  *model.base.scan.config.reference_frequency_hz/LIGHT_KM_S)
        active = [(k, track) for k, ((_, track), index, port) in enumerate(zip(
            model.base.scan.tracks, model.base.assignments, model.base.ports, strict=True))
                  if index < port.candidate_count]
        local = []
        for (k, track), prepared in zip(active, model.prepared, strict=True):
            query, index, rx, n, weights, measured, center = prepared
            position, velocity = query._orbit_states_per_satellite([state[2]+state[5+index]])
            line = position[0, :n]-receiver
            line /= np.linalg.norm(line, axis=1, keepdims=True)
            doppler = factor*np.sum(velocity[0, :n]*line, axis=1)
            rate = state[3+rx]*query.drift_scale
            offset_center = float(weights@(measured-doppler-rate*(query.times[:n]-center)))
            scale_to_actual = track.rf_hz/model.base.scan.config.reference_frequency_hz
            offset_zero = (offset_center-rate*center)*scale_to_actual
            channel = int(track.observation_ids[0].split(':channel')[1].split(':')[0])
            local.append(dict(unit=unit, track=k, receiver=rx, channel=channel,
                rf_hz=float(track.rf_hz), satellite_index=index, center_s=float(center),
                offset_at_scan_zero_actual_hz=offset_zero,
                wrapped_offset_hz=float(wrap(offset_zero)), parent_sha256=digest(path)))
        rows.extend(local)
        for label, keys in [('receiver_channel', ['receiver', 'channel', 'rf_hz']),
                            ('receiver_channel_satellite',
                             ['receiver', 'channel', 'rf_hz', 'satellite_index'])]:
            buckets = defaultdict(list)
            for row in local:
                buckets[tuple(row[k] for k in keys)].append(row)
            for key, members in buckets.items():
                offsets = np.array([r['wrapped_offset_hz'] for r in members])
                phasors = np.exp(2j*np.pi*offsets/PERIOD)
                errors = []
                if len(members) >= 3:
                    for i, value in enumerate(offsets):
                        donors = np.delete(phasors, i).sum()
                        if abs(donors) < 1e-12:
                            continue
                        prediction = np.angle(donors)*PERIOD/(2*np.pi)
                        errors.append(abs(float(wrap(value-prediction))))
                groups.append(dict(unit=unit, grouping=label, key=list(key), n=len(members),
                    circular_resultant=float(abs(phasors.mean())),
                    donor_absolute_errors_hz=errors))
    verify_sources(sources)
    summary = {}
    for label in ['receiver_channel', 'receiver_channel_satellite']:
        selected = [g for g in groups if g['grouping'] == label]
        errors = [e for g in selected for e in g['donor_absolute_errors_hz']]
        summary[label] = dict(groups=len(selected),
            eligible_groups=sum(bool(g['donor_absolute_errors_hz']) for g in selected),
            eligible_tracks=len(errors),
            median_error_hz=float(np.median(errors)) if errors else None,
            p90_error_hz=float(np.percentile(errors, 90)) if errors else None,
            within_200_hz=sum(e <= 200 for e in errors),
            within_1000_hz=sum(e <= 1000 for e in errors))
    result = dict(rows=rows, groups=groups, summary=summary, source_sha256=sources,
        elapsed_s=time.monotonic()-started,
        qualification='Descriptive fitted-offset coherence, no GPS or new fit. GLS offsets '
        'use original training samples at frozen inferred states/identities. Undo canonical '
        'RF scaling and translate receiver drift to scan-time zero before modulo alias period. '
        'Donor means exclude target offset but shared inferred state uses all tracks, so '
        'this is not held-out validation or hardware calibration. Threshold counts descriptive; '
        'unknown transmitter offsets, identity error and detection aliases remain confounded.')
    output = HERE/'frequency-offset-coherence-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(dict(summary=summary, elapsed_s=result['elapsed_s']), indent=2))


if __name__ == '__main__':
    main()
