"""Check cached CH5 row provenance; artifacts and source only."""
import ast
import hashlib
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024')
COMPONENT = 'DS24-0013-RX2-CH5-T001-RF11940312500.000000'
CODE = Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools/run_algo01_ds23_sample.py')


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vector_sha(value):
    return hashlib.sha256(json.dumps(value, separators=(',', ':')).encode()).hexdigest()


def main():
    began = time.monotonic()
    initial_path = SOURCE / 'DS24-0013/fit_radio_noise.json'
    result_path = SOURCE / 'DS24-0013/result.json'
    parent_path = SOURCE / 'family_cavity/position/DS24-0013.json'
    initial, result, parent = map(read, (initial_path, result_path, parent_path))
    selected = initial['choices'][initial['selected_hypothesis']]
    find = lambda rows: next(row for row in rows if row['component'] == COMPONENT)
    old = find(selected['node']['seed']['rows'])
    new = find(result['final_node']['seed']['rows'])
    later = find(parent['baseline_node']['seed']['rows'])
    changed = [key for key in old if old[key] != new[key]]
    tree = ast.parse(CODE.read_text())
    relabel_calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute) and node.func.attr == 'update'
                    and {k.arg for k in node.keywords} == {'candidate_index', 'candidate_norad'}]
    trim = find(result['trims'])
    suffix = next(row for row in trim['alternatives'] if row['start_index'] == 26 and row['stop_index'] == 57)
    metrics = {arm: find(selected['arms'][arm]['metrics']['tracks']) for arm in ('c0', 'fitted_c')}
    checks = [
        dict(name='selected original candidate is65871; cached row relabeled57450',
             passed=initial['selected_hypothesis'] == 0 and old['candidate_norad'] == 65871 and new['candidate_norad'] == later['candidate_norad'] == 57450),
        dict(name='only candidate labels changed; every residual/metric field identical',
             passed=sorted(changed) == ['candidate_index', 'candidate_norad'] and new == later),
        dict(name='cached vectors and scalar RMS/bias exactly carried forward',
             passed=all(old[k] == new[k] == later[k] for k in ('residual_hz', 'innovations_hz', 'times_s', 'rms_hz', 'bias_hz', 'cost'))),
        dict(name='saved scientific source matches current relabel implementation',
             passed=sha(CODE) == result['source_sha256'] and len(relabel_calls) == 1),
        dict(name='old genuine fitted metrics concern65871 and fail',
             passed=all(q['norad'] == 65871 and not q['compatible'] for q in metrics.values())),
        dict(name='57450 partial salvage exists but final source entirely rejected',
             passed=trim['candidate_count'] == 35 and trim['supports_tested'] == 78 and
             trim['selected']['norad'] == 57450 and trim['selected']['points'] == 32 and
             suffix['norad'] == 57450 and suffix['points'] == 31 and
             COMPONENT in result['post_salvage_history'][0]['rejected_components'] and
             all(find(result['arms'][a]['record']['tracks'])['points'] == 0 for a in ('c0', 'fitted_c'))),
    ]
    receipt = dict(all_passed=all(q['passed'] for q in checks), checks=checks,
        original_seed_norad=old['candidate_norad'], relabeled_seed_norad=new['candidate_norad'],
        cached_RMS_hz=old['rms_hz'], cached_bias_hz=old['bias_hz'], changed_fields=changed,
        cached_vector_hashes={key: vector_sha(old[key]) for key in ('residual_hz', 'innovations_hz', 'times_s')},
        original_fitted65871_RMS_hz={a: q['native_rms_hz'] for a, q in metrics.items()},
        partial_salvage=trim, post_salvage_rejection=result['post_salvage_history'][0],
        final_kept_points={a: find(result['arms'][a]['record']['tracks'])['points'] for a in ('c0', 'fitted_c')},
        relabel_source_line=relabel_calls[0].lineno,
        bindings={str(p): sha(p) for p in (CODE, initial_path, result_path, parent_path, Path(__file__))},
        seconds=time.monotonic() - began, propagation_calls=0, position_fits=0, geographic_truth_read=False,
        conclusion='2442.510071 Hz is an original65871 cached seed residual later tagged57450; it is not a regenerated57450 orbit residual. Whole-source57450 qualification still failed after partial salvage; new causal evidence is unaffected.')
    output = HERE / 'archival_check.json'
    with output.open('x') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(path=str(output), all_passed=receipt['all_passed'], seconds=receipt['seconds'], failed=[q for q in checks if not q['passed']])))


if __name__ == '__main__':
    main()
