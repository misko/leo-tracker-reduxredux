"""Publish four shared-model orbit PNGs from immutable inference evidence."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.regional_position_bank import build_regional_bank
from leo.application.shared_fast_position import prepare_views
from leo.application.shared_orbit_replay import orbit_lanes, selected_model
from leo.cli.shared_fast_position import load_input
from leo.contracts.digests import sha256_digest
from leo.contracts.regional_position import RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.presentation.fast_scan_orbits import render_fast_scan_orbits
from leo.sky.propagation import parse_element_sets
from leo.storage.shared_fast_scan import SharedFastScanStore


def publish(store, job_id, tle_root):
    with store.owner('plots-' + job_id) as acquired:
        if not acquired:
            raise RuntimeError('Shared plot publication already owned')
        job, document, terminal, stages = store.plot_evidence(job_id)
        output = store.orbit_store()
        saved = output.orbit_manifest(job['run_id'])
        if saved['artifacts']:
            if saved['provenance']['terminal_sha256'] != job['terminal']['sha256']:
                raise ValueError('Existing plots belong to another shared result')
            for entry in saved['artifacts']:
                output.orbit_artifact(job['run_id'], entry['name'])
            return saved
        prepared, nodes = prepare_views(load_input(document))
        provenance = terminal['provenance']
        if (prepared['all'].evidence_sha256 != provenance['evidence_sha256']
                or nodes.tolist() != provenance['clock_nodes_s']):
            raise ValueError('Shared prepared observations changed')
        archive = TleArchiveReader(tle_root)
        snapshots = [s for s in archive.list_snapshots()
                     if s.digest == provenance['tle_sha256']
                     and s.collected_utc_ns == provenance['tle_collected_utc_ns']]
        if len(snapshots) != 1:
            raise ValueError('Exact selected TLE snapshot required')
        payload = archive.read(snapshots[0])
        if sha256_digest(payload.encode()) != provenance['tle_payload_sha256']:
            raise ValueError('Selected TLE bytes changed')
        filtered, _ = exclude_labelled_starlink_debris(payload)
        catalogue = parse_element_sets(filtered)
        lookup = {int(n): i for i, n in enumerate(catalogue.satellite_numbers)}
        numbers = terminal['candidate_numbers']
        if numbers != stages['candidate-union']['numbers']:
            raise ValueError('Selected candidate union changed')
        prior = RegionalPrior(**provenance['prior'])
        obs = prepared['all'].observations

        def bank_for(observations):
            bank, _ = build_regional_bank(
                catalogue, [lookup[n] for n in numbers], prepared['all'].start_utc_ns,
                observations, prior, maximum_seconds=60)
            return bank.select([list(bank.numbers).index(n) for n in numbers])

        bank = bank_for(obs)
        model, fit, audit = selected_model(prepared, bank, prior, nodes, terminal, stages)
        extent = replace(obs, times_s=np.linspace(min(0, obs.times_s.min()),
                                                 max(300, obs.times_s.max()), len(obs.times_s)))
        lanes, details = orbit_lanes(model, fit, bank_for(extent))
        title = document.get('provenance', {}).get('recording_name', job['run_id'])
        pngs = render_fast_scan_orbits(
            lanes, title=title, alias_period_hz=1 / 4.4e-6,
            subtitle=f"{store.model_version} · {terminal['selection']['source']} · "
                     'calibration removed · posterior associations')
        # Recheck persisted source and stage hashes before publishing the manifest.
        store.plot_evidence(job_id)
        output.publish_orbits(job['run_id'], pngs, dict(
            **details, model_version=store.model_version, stage=store.model_version,
            job_id=job_id, terminal_sha256=job['terminal']['sha256'],
            input_sha256=job['input_sha256'], snapshot_sha256=provenance['tle_sha256'],
            position=terminal['position'], satellites=numbers, time_limits_s=[0, 300],
            replayed_objective=audit['objective'], strict_stationarity=audit['stationarity']))
        return output.orbit_manifest(job['run_id'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bulk-root', type=Path, required=True)
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--model-version', default='shared-scan-q-v2')
    parser.add_argument('--tle-root', type=Path, default=Path('/var/lib/leo/tle'))
    args = parser.parse_args()
    result = publish(SharedFastScanStore(args.bulk_root, args.model_version),
                     args.job_id, args.tle_root)
    print(json.dumps(dict(run_id=result['run_id'], plots=len(result['artifacts']))))


if __name__ == '__main__':
    main()
