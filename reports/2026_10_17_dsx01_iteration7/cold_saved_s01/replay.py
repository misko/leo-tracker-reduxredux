"""Exact public saved-endpoint replay on ORIGINAL S01 frozen cohorts; no fits."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from metrics import compare, zero_c, rms

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
DATA = REPORTS/'2026_10_16_dsx01_fast_association_losses'
SAVED = Path('/tmp/three-track-investigation/space-track-pipeline-rerun/output')


def sha(path):
    return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()


def plain(value):
    if isinstance(value, np.ndarray):return value.tolist()
    if isinstance(value, np.generic):return value.item()
    if isinstance(value, dict):return {k:plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):return [plain(v) for v in value]
    return value


def save(path, value):
    value = plain(value)
    if path.exists():
        assert json.loads(path.read_text()) == value
        return
    with path.open('x') as stream:json.dump(value, stream, indent=2, allow_nan=False);stream.write('\n')


def main():
    from leo.storage.shared_fast_scan import SharedFastScanStore
    from leo.cli.shared_fast_position import load_input
    from leo.application.shared_fast_position import prepare_views
    from leo.application.shared_orbit_replay import selected_model
    from leo.contracts.regional_position import RegionalPrior
    from leo.analysis.regional_position_bank import build_regional_bank
    from leo.analysis.regional_position_score import coordinates
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_sets
    started = time.monotonic()
    source = next(s for s in json.loads((DATA/'sources.json').read_text()) if s['source_id'] == 'S01')
    job, document, original, old_stages = SharedFastScanStore('/srv/bulk/leo', 'shared-scan-q-v2').plot_evidence(source['job_id'])
    assert job['input_sha256'] == source['tracking_input_sha256']
    assert job['terminal']['sha256'] == source['terminal_sha256']
    saved = json.loads((SAVED/'terminal.json').read_text())
    launch = json.loads((SAVED/'launch.json').read_text())
    assert original['state'] == saved['state'] == 'complete'
    assert original['input_sha256'] == saved['input_sha256'] == launch['input_sha256'] == job['input_sha256']
    saved_input = Path(launch['input_path'])
    assert sha(saved_input) == saved['input_sha256']
    assert json.loads(saved_input.read_text()) == document
    new_stages = {}
    for binding in saved['stage_receipts']:
        path = Path(binding['path'])
        assert sha(path) == binding['sha256']
        new_stages[path.stem] = json.loads(path.read_text())
    assert not saved['unfinished_stages']
    # Freeze complete endpoint states before public model reconstruction/audit or
    # new point metrics. No external station/reference file is read anywhere.
    freeze = dict(source_id='S01', original_job_id=source['job_id'],
        source_input_sha256=job['input_sha256'], saved_input_path=str(saved_input), saved_input_sha256=sha(saved_input),
        original_terminal_sha256=job['terminal']['sha256'], saved_terminal_path=str(SAVED/'terminal.json'),
        saved_terminal_sha256=sha(SAVED/'terminal.json'), saved_launch_sha256=sha(SAVED/'launch.json'),
        endpoints={label:dict(vector=t['selected_fit']['vector'], nuisance=t['selected_fit']['nuisance'],
            selected_source=t['selection'], candidate_numbers=t['candidate_numbers'],
            tle_sha256=t['provenance']['tle_sha256'], prior=t['provenance']['prior'],
            zero_c_vector=zero_c(t['selected_fit']['vector'], t['selected_fit']['nuisance'])[0])
            for label, t in [('original', original), ('saved_space_track', saved)]},
        policy='Immutable saved complete fitted-c endpoints; zero-c is deterministic vector6=0 only, no refit or endpoint selection.',
        saved_stage_receipts=saved['stage_receipts'])
    save(HERE/'freeze.json', freeze)
    inputs = load_input(document);prepared, nodes = prepare_views(inputs);obs = prepared['all'].observations
    frozen_rows = [json.loads(line) for line in (DATA/'context-observations.jsonl').read_text().splitlines()
        if json.loads(line)['source_id'] == 'S01']
    assert len(obs.times_s) == len(frozen_rows) == 4797
    assert list(obs.window_ids) == [r['observation_id'] for r in frozen_rows]
    for key, field, transform in [('times_s', 'time_s', lambda a:a), ('rf_hz', 'actual_rf_hz', lambda a:a),
        ('receiver', 'receiver', lambda a:a-1), ('channel', 'channel', lambda a:a)]:
        np.testing.assert_array_equal(getattr(obs, key), transform(np.array([r[field] for r in frozen_rows])))
    archive = TleArchiveReader(Path('/var/lib/leo/tle'));snapshots = archive.list_snapshots()
    states, models, provenance = {}, {}, {}
    for label, terminal, stages in [('original', original, old_stages), ('saved_space_track', saved, new_stages)]:
        assert prepared['all'].evidence_sha256 == terminal['provenance']['evidence_sha256']
        np.testing.assert_array_equal(nodes, terminal['provenance']['clock_nodes_s'])
        prior = RegionalPrior(**terminal['provenance']['prior'])
        snapshot = next(s for s in snapshots if s.digest == terminal['provenance']['tle_sha256']
            and s.collected_utc_ns == terminal['provenance']['tle_collected_utc_ns'])
        assert snapshot.collected_utc_ns < prepared['all'].start_utc_ns-505_000_000_000
        catalogue_text = archive.read(snapshot)
        assert 'sha256:'+hashlib.sha256(catalogue_text.encode()).hexdigest() == terminal['provenance']['tle_payload_sha256']
        catalogue = parse_element_sets(catalogue_text)
        lookup = {int(n):i for i, n in enumerate(catalogue.satellite_numbers)}
        numbers = list(map(int, terminal['candidate_numbers']))
        bank, receipt = build_regional_bank(catalogue, [lookup[n] for n in numbers], prepared['all'].start_utc_ns,
            obs, prior, maximum_seconds=90.)
        lookup = {int(n):i for i, n in enumerate(bank.numbers)};bank = bank.select([lookup[n] for n in numbers])
        model, fit, audit = selected_model(prepared, bank, prior, nodes, terminal, stages)
        assert audit['accepted']
        v, n = np.array(fit['vector']), np.array(fit['nuisance'])
        np.testing.assert_array_equal(v, freeze['endpoints'][label]['vector'])
        np.testing.assert_array_equal(n, freeze['endpoints'][label]['nuisance'])
        models[label] = model
        point_states = {}
        for arm in ['fitted-c', 'zero-c-diagnostic']:
            vv, nn = (v.copy(), n.copy()) if arm == 'fitted-c' else zero_c(v, n)
            ev, details = model.evaluate_details(vv, nn)
            terms = ev[3];best = terms.responsibilities.argmax(1);row = np.arange(len(best))
            associated = terms.responsibilities[row, best] > terms.clutter_probability
            residual = terms.residual_hz[row, best]
            total = vv[7]+model.basis@vv[8:]
            point_states[arm] = dict(associated=associated, residual_hz=residual,
                satellite_number=bank.numbers[best], best_index=best,
                objective=float(ev[0]), likelihood_nll=float(terms.nll),
                vector=vv, nuisance=nn, common_timing_s=float(vv[7]),
                relative_timing_rms_s=rms(total-vv[7]), total_timing_s={str(int(k)):float(t) for k, t in zip(bank.numbers, total)},
                c=float(vv[6]), detection_probability=details['detection_probability'],
                detection_probability_sum=float(details['detection_probability'].sum()),
                sigma_hz_range=[float(np.min(details['sigma_hz'])), float(np.max(details['sigma_hz']))],
                position=dict(zip(['latitude_deg', 'longitude_deg'], map(float, coordinates(prior, vv[:2])))))
        if label == 'original':
            reference = dict(np.load(REPORTS/'2026_10_16_dsx01_models/results/S01-full-fitted-c-original.npz'))
            for key in ['associated', 'residual_hz', 'satellite_number']:
                np.testing.assert_array_equal(point_states['fitted-c'][key], reference[key])
        np.savez_compressed(HERE/(label+'.npz'), observation_id=np.array(obs.window_ids), times_s=obs.times_s,
            **{arm+'_'+key:point_states[arm][key] for arm in point_states for key in
                ['associated', 'residual_hz', 'satellite_number']})
        states[label] = point_states
        costs = {key:terminal.get(key) for key in ['elapsed_seconds', 'optimizer_calls', 'actual_objective_calls',
            'prescreen_objective_calls', 'cost_exact', 'cost_scope', 'source_generation_policy']}
        provenance[label] = dict(tle_sha256=snapshot.digest, provider=snapshot.provider,
            tle_collected_utc_ns=snapshot.collected_utc_ns,
            selected_count=len(numbers), regional_candidate_count=len(terminal['provenance']['full_candidate_numbers']),
            candidate_numbers=numbers, audit=audit, selected_source=terminal['selection'],
            saved_costs=costs, propagation=dict(retained_count=len(receipt.retained_numbers),
                invalid_numbers=receipt.invalid_numbers, outside_prior_numbers=receipt.outside_prior_numbers,
                elapsed_s=receipt.elapsed_s),
            fitted=dict(objective=point_states['fitted-c']['objective'], nll=point_states['fitted-c']['likelihood_nll'],
                common_timing_s=float(v[7]), relative_timing_rms_s=point_states['fitted-c']['relative_timing_rms_s'],
                total_timing_s=point_states['fitted-c']['total_timing_s'], c=float(v[6]),
                position=point_states['fitted-c']['position'],
                detection_probability_sum=point_states['fitted-c']['detection_probability_sum'],
                sigma_hz_range=point_states['fitted-c']['sigma_hz_range']),
            zero_c_diagnostic=dict(objective=point_states['zero-c-diagnostic']['objective'],
                nll=point_states['zero-c-diagnostic']['likelihood_nll'],
                optimization_performed=False, endpoint_stationarity_not_claimed=True))
    with (DATA/'membership.csv').open() as stream:members=[r for r in csv.DictReader(stream) if r['source_id']=='S01']
    masks = {'full':np.ones(len(obs.times_s), bool)}
    for region in sorted({r['region_id'] for r in members}):
        ids = {r['observation_id'] for r in members if r['region_id'] == region}
        masks[region] = np.isin(obs.window_ids, list(ids))
    assert [int(masks[key].sum()) for key in ['DSX01-001', 'DSX01-002', 'DSX01-003']] == [86, 35, 27]
    masks['requested'] = np.logical_or.reduce([masks[key] for key in masks if key.startswith('DSX01')])
    masks['outside_requested'] = ~masks['requested']
    comparisons = {arm:{label:compare(states['original'][arm], states['saved_space_track'][arm], mask)
        for label, mask in masks.items()} for arm in ['fitted-c', 'zero-c-diagnostic']}
    original_ids = set(original['candidate_numbers']);saved_ids = set(saved['candidate_numbers']);shared = sorted(original_ids & saved_ids)
    result = dict(source_id='S01', freeze_sha256=sha(HERE/'freeze.json'),
        original_denominators=dict(full=4797, requested=148, windows={'DSX01-001':86, 'DSX01-002':35, 'DSX01-003':27}),
        all_frozen_row_ids_times_rf_receivers_exact=True,
        provenance=provenance, comparisons=comparisons,
        candidates=dict(original_count=len(original_ids), saved_count=len(saved_ids), shared_count=len(shared), shared=shared,
            original_only=sorted(original_ids-saved_ids), saved_only=sorted(saved_ids-original_ids)),
        classifier='Maximum satellite responsibility strictly exceeds clutter posterior; original125Hz density and exact saved learned q/normalizer retained.',
        c0_policy='Deterministic c coordinate zeroing at both saved complete endpoints; every other parameter and bank unchanged. No c0 refit or matched optimization ablation.',
        no_station_reference_read=True, new_fit_count=0, code_sha256={name:sha(HERE/name) for name in ['replay.py', 'metrics.py']},
        input_sha256={name:sha(DATA/name) for name in ['membership.csv', 'context-observations.jsonl', 'sources.json']},
        elapsed_seconds=time.monotonic()-started,
        qualification='Saved fresh full-recording cold endpoint is evaluated on the original unfiltered DSX01 cohorts. Assignments/identity changes are model outputs, not truth. Provider, catalogue/bank, discovery starts, calibration, timing, q and geography are confounded; no provider-only or localization-accuracy conclusion.')
    save(HERE/'results.json', result)
    print(json.dumps(plain(dict(comparisons=comparisons, candidates=result['candidates'], elapsed_seconds=result['elapsed_seconds'])), indent=2))


if __name__ == '__main__':main()
