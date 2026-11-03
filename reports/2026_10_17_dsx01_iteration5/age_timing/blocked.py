"""Four TRAIN-only continuations; freeze all predictions before held scoring."""

import argparse
import csv
import importlib
import importlib.util
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from leo.analysis.shared_scan_model import density
from leo.contracts.regional_position import PositionObservations

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

HERE = Path(__file__).resolve().parent
BLOCKED = HERE.parent/'blocked_cold'
ATTEMPT = BLOCKED/'S03-block20-parity0'
DATA = HERE.parents[1]/'2026_10_16_dsx01_fast_association_losses'
sys.path.insert(0, str(BLOCKED))
training = importlib.import_module('training_context')
spec = importlib.util.spec_from_file_location('age_warm_ports', HERE/'run.py')
warm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(warm)
digest, common, age = warm.digest, warm.common, warm.age


def metadata_from_rows(rows):
    """Ignore measured CFO, gate, confidence and full-fit descriptive labels."""
    return PositionObservations(tuple(r['observation_id'] for r in rows),
        np.array([r['time_s'] for r in rows]), np.zeros(len(rows)),
        np.array([r['actual_rf_hz'] for r in rows]),
        np.array([r['receiver']-1 for r in rows]), np.array([r['channel'] for r in rows]),
        np.ones(len(rows)))


def role_masks(ids, membership):
    roles = {r['global_group_id']: r['role'] for r in membership}
    if len(roles) != len(membership):
        raise ValueError('duplicate role authority')
    masks = {role: np.array([roles[key] == role for key in ids])
             for role in ('train', 'held', 'boundary')}
    if not np.all(sum(m.astype(int) for m in masks.values()) == 1):
        raise ValueError('every observation requires exactly one declared role')
    return masks


def prepare():
    ctx = training.load_training_context()
    derivation = json.loads((ATTEMPT/'derivation.json').read_text())
    authority = derivation['causal_tle']
    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    matches = [s for s in archive.list_snapshots(authority['provider'])
        if s.digest == authority['sha256'] and s.collected_utc_ns == authority['collected_utc_ns']]
    if len(matches) != 1 or matches[0].collected_utc_ns >= derivation['origin_utc_ns']:
        raise ValueError('unique original causal TRAIN catalogue required')
    catalogue = parse_element_sets(archive.read(matches[0]))
    lookup = {int(n): i for i, n in enumerate(catalogue.satellite_numbers)}
    epochs = catalogue.element_epoch_utc_ns()
    selected = np.array([epochs[lookup[int(n)]] for n in ctx.bank.numbers], dtype=np.int64)
    ages = (derivation['origin_utc_ns']-selected)/86400e9
    calibration = json.loads((HERE/'calibration_v2.json').read_text())
    sigmas, statuses = age.widths(matches[0].provider, ages, calibration)
    metadata = dict(provider=matches[0].provider, catalogue_digest=matches[0].digest,
        measurement_start_utc_ns=derivation['origin_utc_ns'], numbers=ctx.bank.numbers,
        element_epoch_utc_ns=selected, signed_age_days=ages, sigmas_s=sigmas, statuses=statuses,
        changed_widths=int(np.sum(sigmas != 2.)), train_observations=len(ctx.observations.times_s),
        terminal_sha256=digest(ATTEMPT/'output/terminal.json'),
        training_input_sha256=digest(ATTEMPT/'training-input.json'))
    return ctx, sigmas, metadata


def freeze():
    paths = [Path(__file__), HERE/'test_blocked.py', HERE/'BLOCKED_PROTOCOL.md',
        HERE/'model.py', HERE/'run.py', HERE/'calibration_v2.json',
        BLOCKED/'training_context.py', BLOCKED/'derive_blocks.py',
        ATTEMPT/'derivation.json', ATTEMPT/'training-input.json', ATTEMPT/'output/terminal.json',
        ATTEMPT/'context-verification.json', common.HERE/'common.py']
    paths += sorted((ATTEMPT/'output/stages').glob('*.json'))
    paths += [HERE.parents[1]/'2026_10_17_dsx01_iteration4/cold_pipeline'/name
              for name in ('evaluate.py', 'support_diagnostics.py')]
    with (HERE/'blocked_plan.json').open('x') as stream:
        json.dump(dict(source_sha256={str(p): digest(p) for p in paths},
            policy='2priorfamilies x2RFarms; TRAIN complete terminal seed; continuation only',
            maximum_evaluations=1000, maximum_seconds=120, optimizer_calls=4,
            no_held_selection=True, unchanged_age_policy=True,
            c0='conditional on fitted-c TRAIN-only source generation'), stream, indent=2)


def verify():
    plan = json.loads((HERE/'blocked_plan.json').read_text())
    if any(digest(path) != sha for path, sha in plan['source_sha256'].items()):
        raise ValueError('frozen blocked pilot authority changed')
    return plan


def qualify():
    verify()
    ctx, sigmas, metadata = prepare()
    v, n = ctx.vector.copy(), ctx.nuisance.copy()
    baseline = ctx.model.evaluate_joint(v, n)
    scalar = age.RelativeTimingModel(ctx.model, 2.).evaluate_joint(v, n)
    target = age.RelativeTimingModel(ctx.model, sigmas).evaluate_joint(v, n)
    for a, b in zip(baseline[:3], scalar[:3], strict=True):
        np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(baseline[3].responsibilities, target[3].responsibilities)
    np.testing.assert_array_equal(baseline[1][:8], target[1][:8])
    np.testing.assert_array_equal(baseline[2], target[2])
    delta = ctx.model.basis@v[8:]
    np.testing.assert_allclose(target[0]-baseline[0],
        .5*np.sum(delta**2*(1/sigmas**2-.25)), atol=1e-7, rtol=0)
    if not np.any(sigmas != 2.):
        raise ValueError('blocked age policy changes no widths; duplicate fits unnecessary')
    verify()
    common.save_json(HERE/'blocked_qualification.json', dict(passed=True,
        metadata=metadata, objectives=3, fits=0,
        public_training_loader='original source validation/preparation additional, not zero prep',
        held_CFO_read=False, source_seed_unmodified=True))


def run(family):
    verify()
    if not json.loads((HERE/'blocked_qualification.json').read_text())['passed']:
        raise ValueError('qualification required')
    base, sigmas, metadata = prepare()
    selected = np.full_like(sigmas, 2.) if family == 'scalar2' else sigmas
    model = age.RelativeTimingModel(base.model, selected)
    outputs = []
    for arm in ('fitted-c', 'zero-c'):
        v, n = base.vector.copy(), base.nuisance.copy()
        if arm == 'zero-c':
            v[6] = 0.
        counter = warm.Counted(model)
        ctx = replace(base, model=counter, fixed_c=arm == 'zero-c', deadline=time.monotonic()+120)
        result = common.refit(ctx, v, n, max_evaluations=1000, max_seconds=120,
                              fixed_c=ctx.fixed_c)
        if counter.calls != result['diagnostics']['evaluations'] or counter.calls > 1000:
            raise ValueError('actual objective budget mismatch')
        audit = common.endpoint_status(replace(ctx, model=model),
                                       result['vector'], result['nuisance'])
        path = HERE/f'blocked_fit_{family}_{arm}.json'
        if path.exists():
            raise FileExistsError('no overwrite/retry')
        common.save_json(path, dict(result, family=family, arm=arm, audit=audit,
            width_metadata=metadata, effective_sigmas_s=selected, independent_terminal_audits=1,
            prediction_policy='plain unchanged base model with newly fitted complete parameters'))
        outputs.append(dict(path=str(path), sha256=digest(path)))
        print(family, arm, audit, counter.calls, flush=True)
    verify()
    common.save_json(HERE/f'blocked_seal_{family}.json', dict(outcomes=outputs))


def fit_seals():
    records = []
    for family in ('scalar2', 'age'):
        seal = json.loads((HERE/f'blocked_seal_{family}.json').read_text())
        if len(seal['outcomes']) != 2:
            raise ValueError('both RF outcomes required for each family')
        seen = set()
        for record in seal['outcomes']:
            if digest(record['path']) != record['sha256']:
                raise ValueError('all4 fitted outcomes must seal before metadata predictions')
            result = json.loads(Path(record['path']).read_text())
            if result['family'] != family or result['arm'] not in ('fitted-c', 'zero-c'):
                raise ValueError('sealed fit identity mismatch')
            if result['arm'] in seen:
                raise ValueError('duplicate sealed RF outcome')
            seen.add(result['arm'])
            records.append(record)
    return records


def predict():
    verify()
    records = fit_seals()
    base, _, _ = prepare()
    fields = ('observation_id', 'time_s', 'actual_rf_hz', 'receiver', 'channel')
    metadata_rows = []
    for line in (DATA/'context-observations.jsonl').read_text().splitlines():
        row = json.loads(line)
        if row['source_id'] == 'S03':
            metadata_rows.append({field: row[field] for field in fields})
    metadata = metadata_from_rows(metadata_rows)
    d = json.loads((ATTEMPT/'derivation.json').read_text())
    masks = role_masks(metadata.window_ids, d['membership'])
    # Held measured values remain zero and never enter this prediction port.
    assert not metadata.measured_hz.any()
    outputs = []
    for record in records:
        result = json.loads(Path(record['path']).read_text())
        v, n = np.array(result['vector']), np.array(result['nuisance'])
        predictions = training.predict_original(base, v, n, metadata)
        path = HERE/f'blocked_predictions_{result["family"]}_{result["arm"]}.npz'
        if path.exists():
            raise FileExistsError('no overwrite')
        np.savez_compressed(path, **predictions, **{role+'_mask': m for role, m in masks.items()})
        outputs.append(dict(path=str(path), sha256=digest(path), fit=record))
    verify()
    common.save_json(HERE/'blocked_prediction_seal.json', dict(outcomes=outputs,
        metadata_source_sha256=digest(DATA/'context-observations.jsonl'),
        policy='all4 predictions frozen using metadata and plain TRAIN base; held CFO not scored'))


def score():
    verify()
    fits = fit_seals()
    seal = json.loads((HERE/'blocked_prediction_seal.json').read_text())
    if (len(seal['outcomes']) != 4 or
            {(r['fit']['path'], r['fit']['sha256']) for r in seal['outcomes']} !=
            {(r['path'], r['sha256']) for r in fits}):
        raise ValueError('exact four-fit prediction inventory required')
    if any(digest(r['path']) != r['sha256'] for r in seal['outcomes']):
        raise ValueError('all4 prediction receipts must seal before held scoring')
    source = DATA/'context-observations.jsonl'
    if digest(source) != seal['metadata_source_sha256']:
        raise ValueError('held metadata/value authority changed')
    rows = [json.loads(line) for line in source.read_text().splitlines()]
    rows = [r for r in rows if r['source_id'] == 'S03']
    metadata = metadata_from_rows(rows)
    measured = np.array([r['measured_cfo_hz'] for r in rows])
    with (DATA/'membership.csv').open() as stream:
        members = [r for r in csv.DictReader(stream) if r['source_id'] == 'S03']
    base, _, _ = prepare()
    results = []
    for record in seal['outcomes']:
        fit = json.loads(Path(record['fit']['path']).read_text())
        with np.load(record['path']) as predictions:
            terms, details = density(measured, predictions['prediction_hz'],
                predictions['visibility_weight'], np.full(len(measured), 125.),
                predictions['detection_probability'], base.model.score)
            masks = {role: predictions[role+'_mask'].copy()
                     for role in ('train', 'held', 'boundary')}
            numbers = predictions['number'].copy()
        best = terms.responsibilities.argmax(axis=1)
        assigned = terms.responsibilities[np.arange(len(best)), best] > terms.clutter_probability
        residual = terms.residual_hz[np.arange(len(best)), best]
        training_nll = base.model.evaluate_joint(np.array(fit['vector']),
                                                  np.array(fit['nuisance']))[3].nll
        np.testing.assert_allclose(details['row_nll'][masks['train']].sum(), training_nll,
                                   atol=1e-6, rtol=0)
        def metric(use, _assigned=assigned, _details=details, _residual=residual):
            use = np.asarray(use, bool)
            chosen = use & _assigned
            return dict(observations=int(use.sum()), associated=int(chosen.sum()),
                frequency_nll=float(_details['row_nll'][use].sum()),
                associated_rms_hz=float(np.sqrt(np.mean(_residual[chosen]**2)))
                    if chosen.any() else None)
        windows = {}
        for region in sorted({r['region_id'] for r in members}):
            ids = {r['observation_id'] for r in members if r['region_id'] == region}
            use = np.isin(metadata.window_ids, list(ids))
            windows[region] = {role: metric(use & mask) for role, mask in masks.items()}
        path = HERE/f'blocked_eval_{fit["family"]}_{fit["arm"]}.npz'
        np.savez_compressed(path, associated=assigned, residual_hz=residual,
            satellite_number=numbers[best], times_s=metadata.times_s,
            **{role+'_mask': mask for role, mask in masks.items()})
        results.append(dict(family=fit['family'], arm=fit['arm'], audit=fit['audit'],
            diagnostics=fit['diagnostics'], **{role: metric(mask) for role, mask in masks.items()},
            windows=windows, train_nll_closure=True, prediction_sha256=record['sha256']))
    common.save_json(HERE/'blocked_evaluation.json', dict(rows=results,
        prediction_seal_sha256=digest(HERE/'blocked_prediction_seal.json'),
        additional_train_objective_checks=4, no_held_fit=True, promotion=False,
        denominator='2073TRAIN+1909HELD+6boundary; held requested80; other sources untested',
        c0_scope='conditional on fitted-c TRAIN-only source generation',
        priors='different-prior J is not model evidence; predictive NLL excludes priors'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('freeze', 'qualify', 'run', 'predict', 'score'))
    parser.add_argument('--family', choices=('scalar2', 'age'))
    args = parser.parse_args()
    {'freeze': freeze, 'qualify': qualify, 'run': lambda: run(args.family),
     'predict': predict, 'score': score}[args.action]()
