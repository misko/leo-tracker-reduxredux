"""Narrow public replay loader for both complete S01 endpoints; no station IO."""
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
DATA = REPORTS/'2026_10_16_dsx01_fast_association_losses'
SAVED = Path('/tmp/three-track-investigation/space-track-pipeline-rerun/output')


def load_contexts(*, maximum_seconds=110.):
    """Return {'original':Context, 'saved_space_track':Context}, strict replay.

    These are complete fitted states, not inferred new states. This function
    only reads; it never runs a pipeline, chooses a state, or accesses station
    configuration. Public source/archive inputs are required, not hardware.
    """
    sys.path.insert(0, str(REPORTS/'2026_10_16_dsx01_models'))
    from common import Context
    from leo.storage.shared_fast_scan import SharedFastScanStore
    from leo.cli.shared_fast_position import load_input
    from leo.application.shared_fast_position import prepare_views
    from leo.application.shared_orbit_replay import selected_model
    from leo.contracts.regional_position import RegionalPrior
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.analysis.regional_position_score import coordinates
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets
    if not 0 < maximum_seconds <= 120:
        raise ValueError('Positive read allowance no greater than120seconds required')
    deadline = time.monotonic()+maximum_seconds
    source = next(s for s in json.loads((DATA/'sources.json').read_text()) if s['source_id']=='S01')
    job, document, original, original_stages = SharedFastScanStore('/srv/bulk/leo', 'shared-scan-q-v2').plot_evidence(source['job_id'])
    saved = json.loads((SAVED/'terminal.json').read_text())
    assert job['input_sha256'] == source['tracking_input_sha256'] == original['input_sha256'] == saved['input_sha256']
    assert job['terminal']['sha256'] == source['terminal_sha256']
    stages = {}
    for binding in saved['stage_receipts']:
        path = Path(binding['path']);data = path.read_bytes()
        assert 'sha256:'+hashlib.sha256(data).hexdigest() == binding['sha256']
        stages[path.stem] = json.loads(data)
    inputs = load_input(document);prepared, nodes = prepare_views(inputs)
    obs = prepared['all'].observations
    frozen = [r for line in (DATA/'context-observations.jsonl').read_text().splitlines()
        if (r := json.loads(line))['source_id']=='S01']
    assert len(frozen) == len(obs.times_s) == 4797
    assert tuple(r['observation_id'] for r in frozen) == obs.window_ids
    np.testing.assert_array_equal(obs.times_s, [r['time_s'] for r in frozen])
    archive = TleArchiveReader(Path('/var/lib/leo/tle'));snapshots = archive.list_snapshots();contexts = {}
    for label, terminal, receipts in [('original', original, original_stages), ('saved_space_track', saved, stages)]:
        assert terminal['state']=='complete' and terminal['selection']['accepted']
        assert prepared['all'].evidence_sha256 == terminal['provenance']['evidence_sha256']
        np.testing.assert_array_equal(nodes, terminal['provenance']['clock_nodes_s'])
        snapshot = next(s for s in snapshots if s.digest == terminal['provenance']['tle_sha256']
            and s.collected_utc_ns == terminal['provenance']['tle_collected_utc_ns'])
        assert snapshot.collected_utc_ns < prepared['all'].start_utc_ns-505_000_000_000
        text = archive.read(snapshot)
        assert 'sha256:'+hashlib.sha256(text.encode()).hexdigest() == terminal['provenance']['tle_payload_sha256']
        catalogue = parse_element_sets(text);prior = RegionalPrior(**terminal['provenance']['prior'])
        numbers = list(map(int, terminal['candidate_numbers']))
        lookup = {int(n):i for i, n in enumerate(catalogue.satellite_numbers)}
        remaining = deadline-time.monotonic()
        if remaining <= 0:raise TimeoutError('S01 context read allowance exhausted')
        bank, _ = build_regional_bank(catalogue, [lookup[n] for n in numbers], prepared['all'].start_utc_ns,
            obs, prior, maximum_seconds=min(90., remaining))
        lookup = {int(n):i for i, n in enumerate(bank.numbers)};bank = bank.select([lookup[n] for n in numbers])
        model, fit, audit = selected_model(prepared, bank, prior, nodes, terminal, receipts)
        assert audit['accepted']
        vector, nuisance = np.array(fit['vector']), np.array(fit['nuisance'])
        lat, lon = coordinates(prior, vector[:2])
        contexts[label] = Context('S01', model, model, vector, nuisance, obs, bank, prior,
            np.ones(len(obs.times_s), bool), np.array(nodes),
            dict(job_id=source['job_id'], input_sha256=job['input_sha256'], endpoint=label,
                tle_sha256=snapshot.digest, tle_provider=snapshot.provider,
                tle_collected_utc_ns=snapshot.collected_utc_ns, audit=audit,
                original_position=dict(latitude_deg=float(lat), longitude_deg=float(lon)),
                qualification='Saved endpoint position only, not a station reference. No new inference.'))
    return contexts
