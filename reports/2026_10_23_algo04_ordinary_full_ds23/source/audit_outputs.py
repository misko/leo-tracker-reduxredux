"""Read-only checks of saved full-cohort evidence; no model construction or fits."""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import math

OUT = Path(__file__).resolve().parents[1]
SOURCE = Path('/srv/bulk/leo/research/algo04-candidate-20261023')
CONTROL = Path('/srv/bulk/leo/research/algo04-controlled-tests-20261023')
ARMS = ('c0', 'fitted_c')
EXCEPTIONS = {'DS23-0068': 'reference_unqualified', 'DS23-0004': 'frozen_bank_incomplete'}
TOLERANCES = dict(objective_difference=1e-5, density_difference=2e-3,
                  coefficient_equation_error=1e-4, predictive_dense_covariance_difference=2e-3)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def finite_fit(saved):
    for key in ['endpoint_east_north_km', 'endpoint_latlon']:
        require(len(saved[key]) == 2 and all(math.isfinite(x) for x in saved[key]), 'nonfinite endpoint')
    require(math.isfinite(saved['negative_twice_elbo']), 'nonfinite objective')


def ids(coverage):
    values = coverage['accepted_observation_ids']
    require(len(values) == len(set(values)) == coverage['associated'], 'duplicate IDs or associated count')
    require(0 <= len(values) <= coverage['total_GLRT'], 'invalid denominator')
    require(abs(coverage['percent']-100*len(values)/coverage['total_GLRT']) < 1e-9, 'association percentage')
    return set(values)


def preserve(parent, child):
    for arm in ARMS:
        require(ids(parent[arm]) <= ids(child[arm]), 'dropped parent ID: '+arm)
        require(parent[arm]['total_GLRT'] == child[arm]['total_GLRT'], 'denominator changed')


def status_check(case, status, complete):
    if case in EXCEPTIONS:
        require(status == EXCEPTIONS[case] and not complete, 'inherited exception mislabeled: '+case)
    else:
        require(status in ['complete', 'execution_fallback'], 'unexpected exception status: '+case)
        require(complete == (status == 'complete'), 'search completion mislabeled: '+case)


def audit_records(case, records, methods):
    expected = {(method, arm) for method in methods for arm in ARMS}
    require(len(records) == len(expected) and {(x['method'], x['arm']) for x in records} == expected, 'required arm audit records missing')
    maxima = collections.defaultdict(float)
    for row in records:
        require(row['case'] == case and row['all_original_gates_replayed'], 'gate replay missing')
        for key, tolerance in TOLERANCES.items():
            value = abs(row[key])
            require(math.isfinite(value) and value <= tolerance, 'audit tolerance: '+key)
            maxima[key] = max(maxima[key], value)
    return maxima


def compare_pair(new, old):
    differences = {}
    for arm in ARMS:
        a, b = new['arms'][arm], old['arms'][arm]
        delta = max(abs(x-y) for x, y in zip(a['endpoint_east_north_km'], b['endpoint_east_north_km'], strict=True))
        require(delta <= 1e-8, 'bounded-study endpoint parity failed')
        require(abs(a['negative_twice_elbo']-b['negative_twice_elbo']) < 1e-5, 'bounded-study objective parity failed')
        require(ids(new['coverage'][arm]) == ids(old['coverage'][arm]), 'bounded-study ID parity failed')
        differences[arm] = delta
    return differences


def audit(out=OUT):
    protocol_path = out/'protocol.json'; protocol = read(protocol_path)
    cases = protocol['cases']; unavailable = ['DS23-0012', 'DS23-0184', 'DS23-0286']
    expected = {f'DS23-{n:04d}' for n in range(1, 414)}-set(unavailable)
    require(len(cases) == 410 and set(cases) == expected and protocol['unavailable'] == unavailable, 'cohort manifest changed')
    require({p.parent.name for p in (out/'raw').glob('*/result.json')} == expected, 'missing or extra case outputs')
    protocol_hash = sha(protocol_path); driver_hash = sha(out/'source/run_full.py')
    maxima = collections.defaultdict(float); counts = collections.Counter(); failures = []; inherited = []; receipts = {}; parity = {}
    bounded_cases = read(CONTROL/'protocol.json')['cases']
    for case in cases:
        folder = out/'raw'/case; result_path = folder/'result.json'; r = read(result_path)
        require(r['case'] == case, 'case receipt mismatch')
        require(r['driver_sha256'] == driver_hash and r['protocol_sha256'] == protocol_hash, 'driver/protocol receipt mismatch')
        receipts[case] = sha(result_path)
        source_path = SOURCE/'raw'/case/'result.json'
        require(sha(source_path) == protocol['input_hashes'][case][str(source_path)], 'frozen source result changed')
        require(r['reference'] == read(source_path)['reference'], 'reference changed')
        status_check(case, r['status'], r['search_complete']); counts[r['status']] += 1
        require(r['no_evaluation_GPS_used'] and r['matched_c_arms'] and r['native_algorithm_unchanged'], 'scientific declarations missing')
        for stage in ['reference', 'ordinary_graph', 'final']:
            require(set(r[stage]['arms']) == set(ARMS) and set(r[stage]['coverage']) == set(ARMS), 'arm mismatch')
            for arm in ARMS:
                finite_fit(r[stage]['arms'][arm]); ids(r[stage]['coverage'][arm])
        preserve(r['reference']['coverage'], r['final']['coverage'])
        if r['status'] != 'complete':
            compare_pair(r['final'], r['reference'])
            if case in EXCEPTIONS:
                method = 'deadline_reference_fallback' if case == 'DS23-0004' else 'reference'
                inherited_rows = r['inherited_audits']
                require(inherited_rows == read(source_path)['audits'], 'inherited audit evidence changed')
                for key, value in audit_records(case, inherited_rows, [method]).items():
                    maxima[key] = max(maxima[key], value)
                counts['inherited_reused_audit_records'] += len(inherited_rows)
            (failures if r['status'] == 'execution_fallback' else inherited).append(dict(case=case, status=r['status'], reason=r.get('reason'), error=r.get('error')))
            continue
        graph = r['ordinary_graph']; final = r['final']; selected = graph['selected']
        preserve(r['reference']['coverage'], graph['coverage']); preserve(graph['coverage'], final['coverage'])
        require(final['node'] == graph['node'] and final['mask'] == graph['mask'] and final['means'] == graph['means'], 'native changed graph likelihood configuration')
        # A single shared mask and entry list defines the observations for both c arms.
        require(final['entries'][:len(graph['entries'])] == graph['entries'], 'native changed parent entries')
        counts['graph_changed'] += selected is not None
        if selected:
            require(selected['paired_valid'] and selected['parent_IDs_preserved'], 'unqualified graph selected')
            require(graph['selected_name'] == selected['name'], 'selected graph name mismatch')
            compare_pair(graph, selected)
            require(all(graph[key] == selected[key] for key in ['node', 'mask', 'means', 'entries']), 'selected graph configuration changed')
            preserve(r['reference']['coverage'], selected['coverage'])
            for arm in ARMS:
                require(selected['arms'][arm]['final_phase_change_s'] <= .01, 'graph phase convergence')
        records = r['audits']
        for key, value in audit_records(case, records, ['reference', 'ordinary_graph', 'final']).items():
            maxima[key] = max(maxima[key], value)
        primary = read(folder/'native'/(case+'.json'))['methods']['persistent5s']
        rescue = read(folder/'native_feasibility'/(case+'.json'))
        chosen = rescue if rescue.get('accepted') else primary
        require(r['native_accepted'] == bool(chosen.get('accepted')) and r['native_constrained_rescue'] == bool(rescue.get('accepted')), 'native status mismatch')
        counts['native_accepted'] += r['native_accepted']; counts['native_rescue_accepted'] += bool(rescue.get('accepted')); counts['native_rescue_eligible'] += bool(rescue.get('eligible'))
        if chosen.get('accepted'):
            require(chosen['paired_valid'], 'native pair not qualified')
            compare_pair(final, chosen)
            fragments = chosen.get('selected_paths') or read(folder/'native'/(case+'_persistent5s_selection.json'))['selected']
            added = final['entries'][len(graph['entries']):]
            require(len(added) == len(fragments), 'native entry/path count changed')
            path_ids = []
            for entry, fragment in zip(added, fragments, strict=True):
                require(entry['component'] == fragment['key'] and entry['candidate_index'] == fragment['candidate_index'] and entry['norad'] == fragment['norad'], 'native path identity changed')
                require(entry['observation_ids'] == fragment['observation_ids'] and entry['points'] == len(fragment['times']) == len(fragment['values']) == len(fragment['observation_ids']), 'native observations changed')
                path_ids.extend(entry['observation_ids'])
            require(len(path_ids) == len(set(path_ids)), 'duplicate native path IDs')
            for arm in ARMS:
                require(set(path_ids) <= ids(final['coverage'][arm]), 'native IDs absent from arm coverage')
                phase = final['arms'][arm]['final_phase_change_s']
                require(math.isfinite(phase) and phase <= .01, 'native phase convergence')
        else:
            compare_pair(final, graph)
            require(final['entries'] == graph['entries'], 'rejected native entries retained')
        if case in bounded_cases:
            old_final = read(CONTROL/'raw'/case/'native.json')['methods']['norescue']
            old_selected = read(CONTROL/'raw'/case/'norescue.json')['selected']
            old_name = old_selected['name'] if old_selected else 'reference'
            require(graph['selected_name'] == old_name, 'bounded-study graph choice changed')
            parity[case] = dict(graph_name=old_name, final_endpoint_difference_km=compare_pair(final, old_final))
            if old_selected:
                parity[case]['graph_endpoint_difference_km'] = compare_pair(graph, old_selected)
    require(set(parity) == set(bounded_cases), 'all five bounded-study parity checks required')
    return dict(all_passed=not failures, all_terminal=True, numerical_audits_valid=True,
                all_scientific_searches_complete=counts['complete'] == 410,
                all_eligible_searches_complete=not failures,
                audited_completed_cases=counts['complete'], inherited_cases=len(inherited),
                cases=410, unavailable=unavailable, counts=dict(counts), failures=failures, inherited=inherited,
                maximum_audit_differences=dict(maxima), bounded_study_parity=parity,
                result_sha256=receipts, protocol_sha256=protocol_hash, driver_sha256=driver_hash,
                inherited_audit_note='Both c-arm reference audit records for each inherited exception are reused verbatim from hash-verified frozen results, checked against original tolerances, and not recomputed.',
                note='Matched likelihood mask and entries are shared; post-fit coverage IDs may differ between c arms.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--out', type=Path, default=OUT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or args.out/'evidence/output_audit.json'
    try:
        report = audit(args.out)
    except Exception as error:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(dict(all_passed=False, numerical_audits_valid=False, error=repr(error)), indent=2)+'\n')
        raise
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    print(json.dumps({key: report[key] for key in ['all_passed', 'all_terminal', 'numerical_audits_valid', 'all_scientific_searches_complete', 'cases', 'counts']}, indent=2))
