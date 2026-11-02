"""Bounded real RF replay of a saved positive research case, never publication.

Only private input labels and the public-terminal preflight adapter differ.
Every numerical call uses the ALGO07 port. Causal history is copied from the
frozen research exports, with original requests checked again after inference.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import time

import numpy as np
from algo07_science import runner
from algo07_science.validation import clean


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SOURCE = Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_01_ds26_ds27_causal_variants')
FROZEN = REPO/'reports/2026_11_01_reconsideration_population/DS26-0066'
READINESS = REPO/'reports/2026_11_01_promotion_readiness/validation/DS26-0066'
INPUT = HERE/'input'
OUTPUT = HERE/'attempt2-output'
CASE = 'DS26-0066'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(value), indent=2, allow_nan=False)+'\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    if OUTPUT.exists():
        raise FileExistsError('Canary output already exists; never resume altered numerical inputs')
    sources = {}
    for source in sorted((REPO/'tools/algo07_science').glob('*')):
        if source.is_file():
            sources[str(source)] = sha(source)
    sources[str(Path(__file__).resolve())] = sha(Path(__file__).resolve())
    for relative, target in [('inputs/'+CASE+'.json', 'inputs/SCAN.json'),
                             ('catalogues/'+CASE+'.json', 'catalogues/SCAN.json'),
                             ('position/'+CASE+'/result.json', 'position/SCAN/result.json'),
                             ('screen/'+CASE+'/result.json', 'screen/SCAN/result.json')]:
        source = SOURCE/relative
        destination = INPUT/target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        sources[str(source)] = sha(source)
    z = read(INPUT/'inputs/SCAN.json')
    z['case'] = 'SCAN'
    write(INPUT/'inputs/SCAN.json', z)
    expected = copy.deepcopy(z['baseline_owners'])
    published = read(INPUT/'position/SCAN/result.json')
    decision = published['decisions']['72h_30s']
    if decision['status'] == 'qualified':
        trial = published['trials'][decision['trial']]
        for arm in runner.e.ARMS:
            for oid in trial['entry']['observation_ids']:
                if oid in expected[arm]:
                    raise ValueError('Research ALGO06 owner collision')
                expected[arm][oid] = trial['entry']['norad']
    history_exports = [FROZEN/'incumbent_history/export.json',
                       FROZEN/'62025/62025_to_68047-combined/history/export.json']
    versions = {}
    count = None
    for path in history_exports:
        item = read(path)
        if item['request']['cutoff'] != z['scan_receipt']['cutoff_utc_ns']:
            raise ValueError('Frozen history cutoff mismatch')
        for n, row in item['export']['chosen'].items():
            versions.setdefault(n, []).append(row)
        snapshots = item['export']['snapshot_count']
        if count is not None and snapshots != count:
            raise ValueError('Frozen history snapshot inventory mismatch')
        count = snapshots
        sources[str(path)] = sha(path)
    write(INPUT/'history-bank.json', dict(cutoff_utc_ns=z['scan_receipt']['cutoff_utc_ns'],
          snapshot_count=count, versions=versions,
          scope='Exact reused frozen active/proposed history exports; no live archive reads'))
    write(INPUT/'exports/SCAN/published-algo06.json', dict(research_only=True, public_terminal_available=False))
    baseline = runner.published_baseline(INPUT, 'SCAN')
    write(OUTPUT/'protocol.json', dict(baselines={'SCAN': baseline}, research_only=True,
          public_terminal_available=False, source_case=CASE, source_sha256=sources,
          time_limit_s=1200, numerical_settings=runner.SETTINGS))
    return baseline, expected, history_exports


def main():
    began = time.monotonic()
    baseline, expected, history_exports = prepare()
    def research_preflight(d, z, actual_baseline, terminal):
        assert terminal == dict(research_only=True, public_terminal_available=False)
        for arm, (p, point) in d['problems'].items():
            np.testing.assert_array_equal(point, baseline[arm]['x'])
            if abs(runner.e.objective(p, d, point)-baseline[arm]['objective']) > 1e-4:
                raise ValueError('Research published objective mismatch')
            if z['baseline_owners'][arm] != expected[arm]:
                raise ValueError('Research published owner mismatch')
        return dict(research_only=True, public_terminal_available=False,
                    saved_research_owner_maps_equal=True, saved_research_objectives_equal=True,
                    associated={a:len(expected[a]) for a in runner.e.ARMS})
    runner.preflight_public = research_preflight
    result = runner.run_worker('SCAN', INPUT, OUTPUT)
    comparison = {}
    frozen = read(FROZEN/'result.json')
    selected = result['selected']
    original_selected = frozen['methods']['combined']['selected']
    original = next((r for r in frozen['records']['combined'] if r['name'] == selected), None)
    if selected and original:
        current = next(r for r in result['records'] if r['name'] == selected)
        for arm in runner.e.ARMS:
            actual, reference = current['pair'][arm], original['pair'][arm]
            comparison[arm] = dict(endpoint_east_north_km=actual['x'],
                endpoint_latlon=actual['endpoint_latlon'], objective=actual['objective'],
                frozen_objective=reference['objective'],
                maximum_endpoint_difference_km=float(np.max(np.abs(np.asarray(actual['x'])-reference['x']))),
                objective_difference=float(actual['objective']-reference['objective']),
                native_ids_sha256_equal=actual['native_ids_sha256']==reference['native_ids_sha256'],
                owners_sha256_equal=actual['owners_sha256']==reference['owners_sha256'],
                phase_reference_maximum_difference_s=float(np.max(np.abs(np.asarray(actual['reference'])-reference['reference']))),
                qualified=actual['qualified'], gains=current['gains'][arm])
    used_exports = list((OUTPUT/'SCAN').rglob('export.json'))
    expected_exports = {json.dumps(read(path)['request'], sort_keys=True): read(path)['export'] for path in history_exports}
    export_parity = []
    for path in used_exports:
        actual = read(path)
        reference = expected_exports.get(json.dumps(actual['request'], sort_keys=True))
        export_parity.append(dict(path=str(path), request=actual['request'],
                                  exact_frozen_export_equal=reference is not None and actual['export']==reference))
    passed = bool(selected == original_selected == '62025_to_68047'
                  and result['execution_status']=='complete'
                  and len(comparison)==2
                  and all(abs(row['objective_difference'])<=1e-4
                          and row['maximum_endpoint_difference_km']<=1e-9
                          and row['native_ids_sha256_equal'] and row['owners_sha256_equal']
                          and row['qualified'] for row in comparison.values())
                  and len(export_parity)==2 and all(row['exact_frozen_export_equal'] for row in export_parity))
    summary = dict(research_only=True, public_terminal_available=False,
        source_case=CASE, private_label='SCAN', selected=selected,
        original_research_selected=original_selected, execution_status=result['execution_status'],
        passed=passed, comparisons=comparison, history_export_parity=export_parity,
        guards=result['guards'], seconds=time.monotonic()-began,
        limitations='Saved research positive numerical replay only. No real published ALGO06 public terminal or production promotion is validated here.')
    write(HERE/'attempt2-summary.json', summary)
    print(json.dumps(clean(summary), indent=2), flush=True)
    if not passed:
        raise SystemExit('Real research numerical parity canary did not meet exact frozen parity')


if __name__ == '__main__':
    main()
