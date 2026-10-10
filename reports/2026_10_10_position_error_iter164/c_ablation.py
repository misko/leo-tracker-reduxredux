"""Postseal, same-region B1 c diagnostic; never runs localization fits."""

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import evaluation
import postseal_preflight

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BRANCHES = ('native', 'zero')
ARMS = ('zero-c', 'fitted-c')
STARTS = ('association', 'zero-timing', 'own-continuation')
BASINS = ('retained-0', 'retained-1', 'retained-2')
FREEZE_FILES = ('c_ablation.py', 'test_c_ablation.py', 'C_ABLATION_PLAN.md',
                'postseal_preflight.py', 'protocol.json', 'evaluation_protocol.json')


def _read_bound(directory, path, hashes):
    path = Path(path)
    relative = path.relative_to(directory).as_posix()
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != hashes.get(relative):
        raise ValueError('receipt changed after full193 preflight: ' + relative)
    return json.loads(raw)


def _number(value):
    return (isinstance(value, (float, int)) and not isinstance(value, bool)
            and math.isfinite(value))


def _fit(final):
    if not isinstance(final, dict):
        return None
    fit = final.get('fit')
    if not isinstance(fit, dict) or fit.get('converged') is not True:
        return None
    vector = fit.get('vector')
    if not isinstance(vector, list) or len(vector) < 8 or not all(map(_number, vector)):
        return None
    if not _number(fit.get('objective')):
        return None
    if final['arm'] == 'zero-c' and vector[6] != 0:
        return None
    return fit


def _finals(region, basin):
    final_rows = region.get('finals', [])
    if not isinstance(final_rows, list):
        return {}, 'invalid final list'
    finals = {}
    for final in final_rows:
        if not isinstance(final, dict):
            return {}, 'invalid final row'
        key = (final.get('arm'), final.get('start'))
        if key[0] not in ARMS or key[1] not in STARTS or key in finals:
            return {}, 'unknown or duplicate final arm/start'
        if final.get('basin') != basin:
            return {}, 'final basin differs from retained region'
        finals[key] = final
    return finals, None


def _pair(member, branch, basin_index, expected_basin, receipt, phase_status):
    label = member['label']
    key = BASINS[basin_index]
    region = (receipt.get('regions') or {}).get(key) if phase_status == 'complete' else None
    results = []
    finals, structure_error = _finals(region, expected_basin) if isinstance(region, dict) else ({}, None)
    if region is not None and not isinstance(region, dict):
        structure_error = 'invalid retained region'
    for start in STARTS:
        item = dict(label=label, dataset=member['dataset'], branch=branch,
                    retained_region=key, basin=expected_basin, start=start,
                    start_scope=('arm-specific-continuation' if start == 'own-continuation'
                                 else 'strict-matched-seed'),
                    status=None, reason=None, arms={}, frequency={}, position={})
        if phase_status != 'complete':
            item.update(status='phase-unavailable', reason=phase_status)
            results.append(item)
            continue
        if region is None:
            item.update(status='missing-region', reason='completed phase lacks ' + key)
            results.append(item)
            continue
        if structure_error:
            item.update(status='integrity-failure', reason=structure_error)
            results.append(item)
            continue
        left, right = (finals.get((arm, start)) for arm in ARMS)
        for arm, final in zip(ARMS, (left, right), strict=True):
            fit = _fit(final)
            item['arms'][arm] = dict(
                present=final is not None, qualified=fit is not None,
                reason=None if final is None else final.get('reason'),
                fit=fit,
                operation=final,
                seed_audit=None if final is None else final.get('seed_audit'))
        if left is None or right is None:
            item.update(status='missing-arm', reason='one or both named fits absent')
            results.append(item)
            continue
        satellites = left.get('satellites')
        calibration = (region.get('calibrations') or {}).get(expected_basin)
        if (satellites != right.get('satellites')
                or not isinstance(satellites, list) or len(satellites) < 2
                or any(type(number) is not int or number < 0 for number in satellites)
                or len(set(satellites)) != len(satellites)
                or not _number(left.get('calibration_penalty'))
                or left['calibration_penalty'] < 0
                or left['calibration_penalty'] != right.get('calibration_penalty')
                or not isinstance(calibration, dict)):
            item.update(status='integrity-failure', reason='bank or calibration differs')
            results.append(item)
            continue
        item['satellites'] = left['satellites']
        item['calibration_penalty'] = left['calibration_penalty']
        if not all(item['arms'][arm]['qualified'] for arm in ARMS):
            item.update(status='unqualified', reason='one or both named fits unqualified')
            results.append(item)
            continue
        seeds = [item['arms'][arm]['seed_audit'] for arm in ARMS]
        if (any(not isinstance(seed, dict) or not isinstance(seed.get('effective'), list)
                for seed in seeds)
                or (start != 'own-continuation'
                    and seeds[0]['effective'] != seeds[1]['effective'])):
            item.update(status='integrity-failure', reason='named initial seed differs')
            results.append(item)
            continue
        item['effective_seed_equal'] = seeds[0]['effective'] == seeds[1]['effective']
        zero = item['arms']['zero-c']['fit']
        fitted = item['arms']['fitted-c']['fit']
        item['status'] = 'paired'
        item['frequency']['objective_delta_fitted_minus_zero'] = (
            fitted['objective'] - zero['objective'])
        for name in ('posterior_rms_hz', 'signal_windows'):
            a, b = zero.get(name), fitted.get(name)
            item['frequency'][name + '_delta_fitted_minus_zero'] = (
                b - a if _number(a) and _number(b) else None)
        results.append(item)
    return results


def _verify_source_closure(plan, digest):
    freeze = json.loads((HERE / 'C_ABLATION_FREEZE.json').read_text())
    if (set(freeze) != {'numerical_protocol_digest', 'source_sha256'}
            or freeze['numerical_protocol_digest'] != digest
            or not isinstance(freeze['source_sha256'], dict)
            or set(freeze['source_sha256']) != set(FREEZE_FILES)):
        raise ValueError('c ablation successor freeze differs')
    for name in FREEZE_FILES:
        expected = freeze['source_sha256'][name]
        if (not isinstance(expected, str) or len(expected) != 64
                or any(char not in '0123456789abcdef' for char in expected)
                or evaluation.sha(HERE / name) != expected):
            raise ValueError('c ablation successor source changed: ' + name)
    numerical = HERE / 'protocol.json'
    review = json.loads((HERE / 'evaluation_protocol.json').read_text())
    if json.loads(numerical.read_text()) != plan:
        raise ValueError('numerical plan object differs from frozen protocol')
    if (review.get('numerical_protocol_digest') != digest
            or review.get('numerical_protocol_sha256') != evaluation.sha(numerical)):
        raise ValueError('evaluation/numerical protocol differs')
    evaluation.verify_files(review, 'source_sha256')
    for group in ('source_sha256', 'input_sha256', 'evaluation_source_sha256'):
        evaluation.verify_files(plan, group)
    for name, expected in plan.get('runtime', {}).get('sha256', {}).items():
        if evaluation.sha(name) != expected:
            raise ValueError('runtime changed: ' + name)


def build(plan, directory, digest, *, root=ROOT, evaluation_factory=None):
    """Authenticate full193 before inspecting B1 receipts or creating a reference port.

    ``evaluation_factory(plan, rows)`` is injectable for synthetic tests. The
    default is the existing 129/107 authority callback through the 164 port.
    This extractor's own source must be frozen in a successor protocol before
    results from it are treated as an official scientific comparison.
    """
    _verify_source_closure(plan, digest)
    gate = postseal_preflight.preflight(plan, directory, digest, root=root)
    directory = Path(directory)
    hashes = gate['receipt_sha256']
    opportunities = []
    rows = []
    for member in plan['members']:
        label = member['label']
        search = _read_bound(directory, directory / label / 'search' / 'result.json', hashes)
        phases = {'search': search}
        for branch in BRANCHES:
            receipt = _read_bound(directory, directory / label / branch / 'result.json', hashes)
            phases[branch] = receipt
            status = receipt['status']
            if search['status'] == 'complete':
                regions = search.get('searches', {}).get(branch, {}).get('regions')
                if not isinstance(regions, list) or len(regions) != 3:
                    raise ValueError(label + '/' + branch + ': discovery lacks exactly three regions')
                basins = []
                for region in regions:
                    e, n = region.get('east_km'), region.get('north_km')
                    if not _number(e) or not _number(n):
                        raise ValueError(label + '/' + branch + ': nonnumeric retained basin')
                    basins.append('point:' + str(e) + ':' + str(n))
                if len(set(basins)) != 3:
                    raise ValueError(label + '/' + branch + ': duplicate retained basin')
            else:
                basins = [None] * 3
            if status == 'complete' and set(receipt.get('regions') or {}) != set(BASINS):
                raise ValueError(label + '/' + branch + ': completed region set differs')
            for index, basin in enumerate(basins):
                opportunities.extend(_pair(member, branch, index, basin, receipt, status))
        rows.append(dict(label=label, phases=phases))
    if len(opportunities) != 193 * 2 * 3 * 3:
        raise ValueError('incomplete B1 opportunity enumeration')
    api = evaluation.reporter()
    if not api['sealed'](rows):
        raise ValueError('full193 reporter seal required')
    factory = evaluation_factory or api['evaluation_callback']
    evaluate = factory(plan, rows)
    for item in opportunities:
        if item['status'] != 'paired':
            continue
        for arm in ARMS:
            try:
                error = evaluate(item['label'], item['branch'], arm,
                                 item['arms'][arm]['operation'])
                if not _number(error) or error < 0:
                    raise ValueError('invalid geographic error')
                item['position'][arm] = dict(status='complete', error_km=float(error))
            except Exception as exc:
                item['position'][arm] = dict(status='failed', reason=repr(exc))
        if all(item['position'][arm]['status'] == 'complete' for arm in ARMS):
            item['position']['delta_fitted_minus_zero_km'] = (
                item['position']['fitted-c']['error_km']
                - item['position']['zero-c']['error_km'])
    # The pair's operation and fit are raw source material, not compact report
    # fields; remove them after the authority callback has consumed them.
    for item in opportunities:
        for value in item['arms'].values():
            value.pop('operation', None)
            value.pop('fit', None)
    counts = Counter(item['status'] for item in opportunities)
    return dict(scope='Postseal same-region B1 diagnostic; not final B7 c isolation',
                membership=193, expected_opportunities=193 * 2 * 3 * 3,
                primary_matched_seed_opportunities=193 * 2 * 3 * 2,
                arm_specific_continuation_opportunities=193 * 2 * 3,
                opportunity_counts=dict(counts), opportunities=opportunities,
                numerical_protocol_digest=digest, receipt_sha256=hashes,
                preflight_counts=gate['counts'],
                limitations='Own-continuation seeds differ by arm; B1 association is fitted-c-led. '
                            'This extractor must be source-frozen before official use.')
