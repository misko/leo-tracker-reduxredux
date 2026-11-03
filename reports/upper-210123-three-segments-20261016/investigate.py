"""Read-only saved-model replay and conditional carrier-shape diagnosis."""
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'three-track-local-segments-20261016'))
from local_segments import Configuration, extract
from leo.storage.shared_fast_scan import SharedFastScanStore
from leo.cli.shared_fast_position import load_input
from leo.application.shared_fast_position import prepare_views
from leo.application.shared_orbit_replay import selected_model
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_bootstrap import observation_subset
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import circular, ALIAS_HZ
from leo.contracts.regional_position import RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

TARGETS = [('rx1_ch1_65_100', 0, 1, 65., 100.),
           ('rx2_ch2_150_200', 1, 2, 150., 200.),
           ('rx1_ch3_95_127', 0, 3, 95., 127.)]


def save(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def main():
    store = SharedFastScanStore('/srv/bulk/leo', 'shared-scan-q-v2')
    job, document, terminal, stages = store.plot_evidence('bb0433f92daacec744fd80a26a863fb3')
    source = load_input(document)
    prepared, nodes = prepare_views(source)
    obs = prepared['all'].observations
    prior = RegionalPrior(**terminal['provenance']['prior'])
    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    snapshot = next(s for s in archive.list_snapshots()
                    if s.digest == terminal['provenance']['tle_sha256']
                    and s.collected_utc_ns == terminal['provenance']['tle_collected_utc_ns'])
    cat = parse_element_sets(archive.read(snapshot))
    lookup = {int(n): i for i, n in enumerate(cat.satellite_numbers)}
    numbers = terminal['candidate_numbers']
    full, receipt = build_regional_bank(cat, [lookup[n] for n in terminal['provenance']['full_candidate_numbers']],
        prepared['all'].start_utc_ns, obs, prior)
    fi = {int(n): j for j, n in enumerate(full.numbers)}
    bank = full.select([fi[n] for n in numbers])
    model, fit, audit = selected_model(prepared, bank, prior, nodes, terminal, stages)
    v, nuisance = (np.array(fit[k]) for k in ('vector', 'nuisance'))
    evaluation, details = model.evaluate_details(v, nuisance)
    terms = evaluation[3]
    best = terms.responsibilities.argmax(axis=1)
    associated = terms.responsibilities[np.arange(len(best)), best] > terms.clutter_probability
    correction = model.original.correction(v, nuisance[:model.clock_count])
    shifts = np.full(len(full.numbers), v[7])
    for num, shift in zip(numbers, v[7] + model.basis @ v[8:]):
        shifts[fi[num]] = shift
    no_clock = model.original.correction(v, np.zeros(model.clock_count))
    np.savez_compressed(ROOT/'calibration-components.npz', published=correction,
        no_clock=no_clock, raw=np.zeros(len(obs.times_s)))
    save('saved-evidence.json', dict(terminal=terminal, stages=stages,
        nodes_s=np.asarray(nodes).tolist(),fit=fit, audit=audit))
    groups = []
    arrays = dict(times=obs.times_s, measured=obs.measured_hz, correction=correction,
                  receiver=obs.receiver, channel=obs.channel, rf=obs.rf_hz, margin=obs.margin,
                  associated=associated, best_number=np.array(numbers)[best],
                  satellite_posterior=terms.responsibilities[np.arange(len(best)),best],
                  clutter_posterior=terms.clutter_probability,
                  candidate_numbers=full.numbers, shifts=shifts)
    for name, receiver, ch, left, right in TARGETS:
        rows = np.flatnonzero((obs.receiver == receiver) & (obs.channel == ch) &
                             (obs.times_s >= left) & (obs.times_s <= right))
        unassociated = rows[~associated[rows]]
        group = dict(name=name, receiver=receiver+1, channel=ch, interval_s=[left,right], total=len(rows),
                     associated=int(associated[rows].sum()), unassociated=len(unassociated),
                     assignments={str(num): int(np.sum(associated[rows] & (best[rows] == j)))
                                  for j,num in enumerate(numbers) if np.any(associated[rows] & (best[rows] == j))})
        arrays[name+'_all_rows'] = rows
        arrays[name+'_unassociated_rows'] = unassociated
        # Orbit-blind continuity proposals; do not select points by a satellite residual.
        sub = observation_subset(obs, rows)
        config = Configuration(window_s=60., stride_s=10., minimum_points=6,
            minimum_span_s=4., maximum_gap_s=5., random_triples=512)
        proposals = extract(sub,config)['proposals']
        unique = {}
        for proposal in proposals:
            key = tuple(proposal['rows'])
            unique[key] = proposal
        proposals = sorted(unique.values(), key=lambda p:(-len(p['rows']),p['rms_hz']))
        selected = []
        used = set()
        for proposal in proposals:
            if len(set(proposal['rows'])-used) < 6:
                continue
            local = np.array(proposal['rows'])
            global_rows = rows[local]
            used.update(local.tolist())
            selected.append(dict(rows=global_rows.tolist(), count=len(global_rows),
                unassociated=int((~associated[global_rows]).sum()),
                span_s=float(np.ptp(obs.times_s[global_rows])),
                time_limits_s=[float(obs.times_s[global_rows].min()),float(obs.times_s[global_rows].max())],
                quadratic_rms_hz=proposal['rms_hz']))
            if len(selected)==3:
                break
        group['continuity_segments']=selected
        group['extraction_configuration']=asdict(config)
        groups.append(group)
        print(json.dumps(group),flush=True)
    summary = dict(run_id=job['run_id'], recording_id='fast8-auto-20261016-210123-05c5faad-1-upper',
        job_id=job['job_id'], input_sha256=job['input_sha256'],
        terminal_sha256=job['terminal']['sha256'],
        snapshot_sha256=snapshot.digest, snapshot_provider=snapshot.provider,
        snapshot_collection_age_s=(prepared['all'].start_utc_ns-snapshot.collected_utc_ns)/1e9,
        position=terminal['position'], audit=audit, c_hz_per_ghz=float(v[6]),common_timing_s=float(v[7]),
        receiver_band_shift=asdict(model.shift) if hasattr(model,'shift') else None,
        observations=len(obs.times_s), associated=int(associated.sum()),
        retained_candidates=numbers, regional_candidate_count=len(full.numbers), groups=groups,
        qualification='Conditional shape diagnosis at full-scan fitted position and receiver calibration. '
            'No independent satellite-identity or position truth. Temporal tests below are conditional on this full-scan calibration.')
    # All data remain in the analysis directory; no production publication or refit.
    save('baseline.json',summary)
    np.savez_compressed(ROOT/'baseline.npz',**arrays)
    np.savez_compressed(ROOT/'orbit-bank.npz',numbers=full.numbers,nodes=full.nodes_s,
                        positions=full.position_km,velocities=full.velocity_km_s)
    save('context.json',dict(prior=terminal['provenance']['prior'],vector=v.tolist(),
        source_origin_ns=prepared['all'].start_utc_ns, window_ids=list(obs.window_ids),
        time_center_s=obs.time_center_s,rf_center_hz=obs.rf_center_hz))


if __name__=='__main__':
    main()
