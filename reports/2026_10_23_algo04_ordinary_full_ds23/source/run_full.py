"""Frozen ordinary graph control across DS23; GPS is reporting-only.

Reuses exactly experiment.norescue from the published five-case study and
unchanged native recovery. Frozen banks are inputs, not regenerated selections.
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from types import SimpleNamespace
import argparse
import contextlib
import os
import signal
import sys
import time
import traceback
import numpy as np
import experiment as exp
import probe_ds23_iteration010_path_feasibility as feasible
from audit_ds23_iteration013_recovery import check
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = Path(__file__).resolve().parents[1]
SOURCE = exp.SOURCE
CONTROL = Path('/srv/bulk/leo/research/algo04-controlled-tests-20261023')
ARMS = exp.ARMS
PATHS = exp.paths
CANARIES = ['DS23-0256', 'DS23-0041', 'DS23-0404']
CAPS = dict(setup=180, graph=1200, native=300, near_feasible=360, audit=180)


def bank_files(case):
    base = SOURCE/'raw'/case
    return [base/'result.json', base/'single_curve_reentry'/(case+'_positions.json'),
            base/'support_aware_reentry'/(case+'.json')]


def inherited_exception(old, support):
    if old['status'] == 'reference_unqualified':
        return 'reference_unqualified'
    if support is None or support.get('status') != 'complete':
        return 'frozen_bank_incomplete'
    return None


def check_ids(cov, allids):
    for arm in ARMS:
        c = cov[arm]; ids = c['accepted_observation_ids']
        assert len(ids) == len(set(ids)) == c['associated'], 'duplicate/count mismatch'
        assert set(ids) <= allids, 'nonphysical original ID'
        assert c['total_GLRT'] == len(allids), 'denominator changed'
        assert abs(c['percent']-100*len(ids)/len(allids)) < 1e-9


def pack(d, cov, kind, selected=None):
    return dict(arms=d['arms'], coverage=cov, kind=kind, node=d['node'],
                mask=d['keep'], means=d['means'], entries=d['entries'], selected=selected)


def audit_pair(d, kind, label, legacy=False):
    rows = []
    for arm, saved in d['arms'].items():
        p = PATHS.build(d, kind, arm, saved['phase_reference'])
        if legacy:
            from repair_algo04_empty_audit import checked
            rows.append(checked(d, p, arm, saved, label))
        else:
            if not d['entries']:
                if not hasattr(p, 'linear_slices'): p.linear_slices = []
                if 'linear_gates' not in saved: saved = dict(saved, linear_gates=[])
            rows.append(check(d, p, arm, saved, label))
    return rows


def compare_canary(case, result):
    old = read(CONTROL/'raw'/case/'native.json')['methods']['norescue']
    delta = {}
    for arm in ARMS:
        new = result['final']['arms'][arm]; before = old['arms'][arm]
        np.testing.assert_allclose(new['endpoint_east_north_km'], before['endpoint_east_north_km'], rtol=0, atol=1e-8)
        assert abs(new['negative_twice_elbo']-before['negative_twice_elbo']) < 1e-5
        assert result['final']['coverage'][arm]['accepted_observation_ids'] == old['coverage'][arm]['accepted_observation_ids']
        delta[arm] = float(np.max(abs(np.asarray(new['endpoint_east_north_km'])-before['endpoint_east_north_km'])))
    return dict(endpoint_maximum_difference_km=delta, original_IDs_identical=True)


def pipeline(case):
    folder = OUT/'raw'/case; folder.mkdir(parents=True, exist_ok=True)
    dest = folder/'result.json'
    if dest.exists(): raise FileExistsError('preserve frozen output '+case)
    started = time.monotonic(); timing = {}; stage = 'setup'; d = None
    old = read(SOURCE/'raw'/case/'result.json'); reference = old['reference']
    result = dict(case=case, reference=reference, final=reference,
                  ordinary_graph=dict(reference, reference_fallback=True, selected_name='reference'),
                  search_complete=False, source_status=old['status'], timing=timing)
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('bounded '+stage+' deadline')))
    try:
        protocol = read(OUT/'protocol.json')
        for path, expected in protocol['input_hashes'][case].items():
            assert sha(Path(path)) == expected, 'frozen input changed: '+path
        support_path = bank_files(case)[2]
        support = read(support_path) if support_path.exists() else None
        reason = inherited_exception(old, support)
        if reason:
            result.update(status=reason, reason='retain reference; inherited gate or incomplete-bank exception',
                          inherited_audits=old.get('audits', []), original_accepted_IDs_preserved=True)
            return result
        signal.alarm(CAPS[stage]); mark = time.monotonic()
        d, frozen = exp.context(case)
        ids = {o['observation_id'] for o in d['observations']}
        check_ids(reference['coverage'], ids)
        audits = audit_pair(d, 'default', 'reference', legacy=True)
        timing[stage] = time.monotonic()-mark
        stage = 'graph'; signal.alarm(CAPS[stage]); mark = time.monotonic()
        exp.norescue(case)
        graph = read(folder/'norescue.json'); selected = graph['selected']
        parent = exp.apply_trial(d, selected) if selected else d
        cov = selected['coverage'] if selected else reference['coverage']
        kind = selected['kind'] if selected else 'default'
        check_ids(cov, ids); assert exp.preserve(reference['coverage'], cov)
        audits += audit_pair(parent, kind, 'ordinary_graph', legacy=selected is None)
        result['ordinary_graph'] = dict(pack(parent, cov, kind, selected),
            selected_name=selected['name'] if selected else 'reference', reference_fallback=selected is None)
        timing[stage] = time.monotonic()-mark
        PATHS.OUT = folder/'native'; PATHS.OUT.mkdir(exist_ok=True)
        PATHS.runner = SimpleNamespace(configure=lambda: None)
        PATHS.parent = lambda _: (parent, cov, kind, selected)
        stage = 'native'; signal.alarm(CAPS[stage]); mark = time.monotonic()
        PATHS.one(case); signal.alarm(0)
        primary = read(PATHS.OUT/(case+'.json'))['methods']['persistent5s']
        timing[stage] = time.monotonic()-mark
        feasible.OUT = folder/'native_feasibility'; feasible.OUT.mkdir(exist_ok=True)
        feasible.binding = SimpleNamespace(configure=lambda: None, paths=PATHS, OUT=PATHS.OUT)
        stage = 'near_feasible'; mark = time.monotonic()
        feasible.one(case); signal.alarm(0)
        rescue = read(feasible.OUT/(case+'.json'))
        timing[stage] = time.monotonic()-mark
        chosen = rescue if rescue.get('accepted') else primary
        final = parent; final_cov = cov
        if chosen.get('accepted'):
            fragments = chosen.get('selected_paths') or read(PATHS.OUT/(case+'_persistent5s_selection.json'))['selected']
            scan, entries = PATHS.native.append_native_paths(parent['scan'], parent['entries'], fragments, PATHS.native.receiver_basis(parent['scan']))
            final = dict(parent, scan=scan, entries=entries, arms=chosen['arms']); final_cov = chosen['coverage']
            assert exp.qualifies(final['arms']), 'native final qualification changed'
        assert exp.preserve(reference['coverage'], final_cov) and exp.preserve(cov, final_cov)
        check_ids(final_cov, ids)
        stage = 'audit'; signal.alarm(CAPS[stage]); mark = time.monotonic()
        audits += audit_pair(final, kind, 'final', legacy=selected is None and not chosen.get('accepted'))
        if selected is not None or chosen.get('accepted'):
            replay = exp.coverage(final, kind, final['arms'])
            for arm in ARMS:
                assert set(replay[arm]['accepted_observation_ids']) == set(final_cov[arm]['accepted_observation_ids'])
        result.update(status='complete', search_complete=True, final=pack(final, final_cov, kind),
            native_accepted=bool(chosen.get('accepted')), native_constrained_rescue=bool(rescue.get('accepted')),
            original_accepted_IDs_preserved=True, audits=audits)
        if case in CANARIES: result['canary_parity'] = compare_canary(case, result)
        timing[stage] = time.monotonic()-mark
    except Exception as exc:
        result.update(status='execution_fallback', search_complete=False, final=reference,
            failed_stage=stage, error=repr(exc), traceback=traceback.format_exc(),
            original_accepted_IDs_preserved=True, reason='operational failure; retain reference, not scientific rejection')
    finally:
        signal.alarm(0)
        result.update(seconds=time.monotonic()-started, driver_sha256=sha(Path(__file__)),
            protocol_sha256=sha(OUT/'protocol.json'), no_evaluation_GPS_used=True,
            matched_c_arms=True, native_algorithm_unchanged=True)
        write(dest, result)
    return result


def worker(case):
    folder = OUT/'raw'/case; folder.mkdir(parents=True, exist_ok=True)
    with (folder/'execution.log').open('w') as stream, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        r = pipeline(case)
    return {k: r[k] for k in ['case', 'status', 'seconds', 'search_complete']}


def freeze():
    previous = read(SOURCE/'protocol.json'); cases = previous['cases']
    core = {str(ROOT/'tools'/(name+'.py')): digest for name, digest in previous['source_hashes'].items()}
    assert all(sha(Path(p)) == h for p, h in core.items()), 'original core sources changed'
    assert sha(Path(exp.__file__)) == sha(CONTROL/'source/experiment.py'), 'bounded scientific rule changed'
    source_hashes = {str(Path(__file__)): sha(Path(__file__)), str(Path(exp.__file__)): sha(Path(exp.__file__)), **core}
    # Freeze all imported local Python dependencies as well as the core list.
    for module in list(sys.modules.values()):
        f = getattr(module, '__file__', None)
        if f and str(f).startswith(str(ROOT)) and str(f).endswith('.py'):
            source_hashes[str(f)] = sha(Path(f))
    record = dict(name='Ordinary graph plus unchanged native recovery', release_status='unpromoted',
        cases=cases, total_dataset=413, unavailable=previous['unavailable'], workers=16, nice_increment=5,
        input_hashes={c: {str(p): sha(p) for p in bank_files(c) if p.exists()} for c in cases},
        source_hashes=source_hashes, previous_protocol_sha256=sha(SOURCE/'protocol.json'),
        controlled_protocol_sha256=sha(CONTROL/'protocol.json'), canaries=CANARIES,
        budgets='exact published ordinary rule: 5x48 then joint near-feasible trigger 5x40 ordinary SLSQP; unchanged native',
        caps_seconds=CAPS, frozen_catalogue_hypotheses_aliases_priors_and_gates=True,
        no_new_RF_no_future_TLE_no_GPS_inference=True, paired_c0_and_fitted_c=True,
        explicit_inherited_exceptions={'DS23-0068': 'reference_unqualified', 'DS23-0004': 'frozen_bank_incomplete'},
        on_execution_failure='retain reference, disclose incomplete search; never select by GPS',
        regional_center=[37.906, -122.545], regional_width_km=25, cold_start=[0, 0],
        promotion_requirements=previous['promotion_requirements'],
        evaluation='development-informed full-DS23 regression evaluation, not blinded or new-location validation')
    path = OUT/'protocol.json'
    if path.exists():
        frozen = read(path)
        assert frozen == record, 'preserve frozen protocol/source'
    else: write(path, record)
    return record


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--cases', nargs='*')
    parser.add_argument('--workers', type=int, default=16); parser.add_argument('--freeze-only', action='store_true')
    args = parser.parse_args(); protocol = freeze()
    if args.freeze_only: return
    cases = args.cases or protocol['cases']; assert set(cases) <= set(protocol['cases'])
    if not args.cases:
        for case in CANARIES:
            r = read(OUT/'raw'/case/'result.json')
            assert r['status'] == 'complete' and r['canary_parity']['original_IDs_identical'], 'canary parity required'
    pending = [c for c in cases if not (OUT/'raw'/c/'result.json').exists()]
    os.nice(5)
    with ProcessPoolExecutor(max_workers=min(16, args.workers)) as pool:
        rows = []
        for future in as_completed([pool.submit(worker, c) for c in pending]):
            row = future.result(); rows.append(row); print(row, flush=True)
            write(OUT/'progress.json', dict(rows=rows, finished=len(list((OUT/'raw').glob('*/result.json'))), total=410))
    all_rows = []
    for case in protocol['cases']:
        p = OUT/'raw'/case/'result.json'
        if p.exists():
            r = read(p); all_rows.append({k: r[k] for k in ['case', 'status', 'seconds', 'search_complete']})
    write(OUT/'execution.json', dict(rows=all_rows, all_terminal=len(all_rows)==410,
        all_eligible_searches_complete=len(all_rows)==410 and all(r['status'] != 'execution_fallback' for r in all_rows),
        all_scientific_searches_complete=len(all_rows)==410 and all(r['search_complete'] for r in all_rows)))


if __name__ == '__main__': main()
