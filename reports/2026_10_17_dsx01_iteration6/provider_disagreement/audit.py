"""Causal provider disagreement on original selected objects; no RF/position fit."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]


def projected_disagreement(old_position, reference_position, reference_velocity):
    displacement = np.asarray(old_position)-np.asarray(reference_position)
    velocity = np.asarray(reference_velocity)
    speed2 = np.sum(velocity**2, axis=-1)
    if displacement.shape!=velocity.shape or displacement.shape[-1]!=3 or np.any(speed2<=0):
        raise ValueError('Aligned three-dimensional states and nonzero reference speeds required')
    equivalent_seconds = np.sum(displacement*velocity, axis=-1)/speed2
    perpendicular_km = np.linalg.norm(displacement-equivalent_seconds[..., None]*velocity, axis=-1)
    return equivalent_seconds, perpendicular_km


def main():
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    sources_path = REPORTS/'2026_10_16_dsx01_fast_association_losses/sources.json'
    cohort_path = REPORTS/'2026_10_17_dsx01_iteration5/age_audit/pairs.csv'
    sources = json.loads(sources_path.read_text())
    with cohort_path.open() as stream:
        cohort = [r for r in csv.DictReader(stream) if r['method']=='original']
    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    parsed = {}
    rows, snapshots = [], []
    for source in sources:
        group = [r for r in cohort if r['source_id']==source['source_id']]
        epochs = {int(r['recording_midpoint_utc_ns']) for r in group}
        assert len(epochs)==1
        epoch = epochs.pop()
        numbers = sorted(int(r['satellite_number']) for r in group)
        states = {}
        for provider in ['space-track', 'huggingface']:
            cutoff = source['first_sample_estimate_utc_ns']-505_000_000_000
            snapshot = archive.select_latest_before(cutoff, provider=provider)
            assert snapshot.collected_utc_ns<cutoff
            if snapshot.digest not in parsed:
                parsed[snapshot.digest] = parse_element_sets(archive.read(snapshot))
            cat = parsed[snapshot.digest]
            lookup = {int(n):i for i, n in enumerate(cat.satellite_numbers)}
            included = [n for n in numbers if n in lookup]
            position, velocity, valid = propagate_candidate_states(cat, [lookup[n] for n in included],
                epoch, np.array([-.001, 0., .001]), np.array([0.]))
            element_epochs = cat.element_epoch_utc_ns()
            states[provider] = {int(cat.satellite_numbers[i]):(p[0, 1], v[0, 1], int(element_epochs[i]))
                for i, p, v in zip(valid, position, velocity)}
            snapshots.append(dict(source_id=source['source_id'], provider=provider, snapshot_sha256=snapshot.digest,
                collected_utc_ns=snapshot.collected_utc_ns, strict_cutoff_utc_ns=cutoff,
                selected_objects=len(numbers), catalogue_present=len(included), valid=len(valid)))
        for number in numbers:
            record = dict(source_id=source['source_id'], satellite_number=number, recording_midpoint_utc_ns=epoch,
                st_present_valid=number in states['space-track'], hf_present_valid=number in states['huggingface'])
            if record['st_present_valid'] and record['hf_present_valid']:
                st_p, st_v, st_epoch = states['space-track'][number]
                hf_p, _, hf_epoch = states['huggingface'][number]
                seconds, perpendicular = projected_disagreement(hf_p, st_p, st_v)
                record.update(st_signed_element_age_hours=(epoch-st_epoch)/3.6e12,
                    hf_signed_element_age_hours=(epoch-hf_epoch)/3.6e12,
                    hf_minus_st_effective_alongtrack_s=float(seconds), perpendicular_km=float(perpendicular),
                    total_displacement_km=float(np.linalg.norm(hf_p-st_p)))
            rows.append(record)
    assert len(rows)==215
    fields = sorted(set().union(*(r.keys() for r in rows)))
    with (HERE/'pairs.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = []
    for source in sources:
        group = [r for r in rows if r['source_id']==source['source_id']]
        valid = [r for r in group if 'hf_minus_st_effective_alongtrack_s' in r]
        dt = np.array([abs(r['hf_minus_st_effective_alongtrack_s']) for r in valid])
        summary.append(dict(source_id=source['source_id'], original_selected_pairs=len(group), jointly_valid=len(valid),
            abs_effective_seconds_p50_p95_max=np.percentile(dt, [50, 95, 100]).tolist() if len(dt) else [],
            abs_effective_over_2s=int(np.sum(dt>2)), abs_effective_over_10s=int(np.sum(dt>10)),
            perpendicular_km_p50_p95_max=np.percentile([r['perpendicular_km'] for r in valid], [50, 95, 100]).tolist() if len(valid) else []))
    receipt = dict(summary=summary, snapshots=snapshots, inputs={str(p):'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [sources_path, cohort_path, Path(__file__)]},
        qualification='Original selected cohort, not independent prior calibration. Compare latest causal snapshots per provider at the recording midpoint. Space-Track is a consistency reference, not truth. Projected ECEF displacement is not a fitted timing correction; large perpendicular differences invalidate pure along-track interpretation. No measured RF, fitted timings or station coordinates are used. No model/provider selected from localization performance.')
    (HERE/'summary.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__=='__main__':
    main()
