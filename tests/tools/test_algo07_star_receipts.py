import copy
import json

import pytest
from algo07_star_receipts import audit_catalogue, audit_group


def records(root=100, child=101, supervisor=99, path='/a'):
    return [(f'{root}.json', dict(pid=root, parent_pid=supervisor, read_paths=[path+'/input.json'],
                                 python_spawns=['/python'], denied_paths=[])),
            (f'{child}.json', dict(pid=child, parent_pid=root, read_paths=[path+'/fit.json'],
                                  python_spawns=[], denied_paths=[]))]


def test_pid_changes_preserve_work_and_ancestry():
    a = audit_group(records(), store_root='/a')
    b = audit_group(records(200, 201, 199, '/b'), store_root='/b')
    assert a['forest'] == b['forest']
    assert a['forest_sha256'] == b['forest_sha256']
    assert a['expected'] == a['receipts'] == 2


def test_missing_spawned_child_is_rejected():
    with pytest.raises(ValueError, match='missing child'):
        audit_group(records()[:1], store_root='/a')


def test_denied_read_is_never_waived():
    bad = records()
    bad[0][1]['denied_paths'] = ['/another/answer.json']
    with pytest.raises(ValueError, match='denied read'):
        audit_group(bad, store_root='/a')


def test_different_read_evidence_changes_the_proof():
    a = records()
    b = copy.deepcopy(a)
    b[1][1]['read_paths'] = ['/a/another-fit.json']
    assert (audit_group(a, store_root='/a')['forest_sha256'] !=
            audit_group(b, store_root='/a')['forest_sha256'])


def test_cycle_is_rejected_even_with_matching_launch_counts():
    bad = records()
    bad[0][1]['parent_pid'] = 101
    bad[1][1]['python_spawns'] = ['/python']
    with pytest.raises(ValueError, match='supervisor'):
        audit_group(bad, store_root='/a')


def catalogue(tmp_path, *, root='/a', pid=100):
    result = {}
    for group, rows in [('ALGO02/worker/read_receipts', records(pid, pid+1, pid-1, root)),
                        ('ALGO03/worker/read_receipts', records(pid+10, pid+11, pid+9, root))]:
        for filename, record in rows:
            if group.startswith('ALGO03'):
                record['read_paths'] = sorted([root+'/ALGO02/read_receipts/'+f'{pid}.json',
                                              root+'/ALGO02/read_receipts/'+f'{pid+1}.json'])
            path = tmp_path/group/filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record))
            result[group+'/'+filename] = dict(path=path, store_root=root,
                source_path=root+'/'+group.split('/')[0]+'/read_receipts/'+filename)
    return result


def test_nested_receipt_reads_are_resolved_by_verified_work(tmp_path):
    a, _ = audit_catalogue(catalogue(tmp_path/'a'))
    b, _ = audit_catalogue(catalogue(tmp_path/'b', root='/b', pid=200))
    assert {k: v['forest'] for k, v in a.items()} == {k: v['forest'] for k, v in b.items()}


def test_unknown_read_receipt_is_rejected(tmp_path):
    items = catalogue(tmp_path)
    path = items['ALGO03/worker/read_receipts/110.json']['path']
    data = json.loads(path.read_text())
    data['read_paths'] = ['/a/ALGO02/read_receipts/999.json']
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='unexported'):
        audit_catalogue(items)


def test_changed_nested_work_is_not_hidden_by_pid_normalization(tmp_path):
    a, _ = audit_catalogue(catalogue(tmp_path/'a'))
    items = catalogue(tmp_path/'b', root='/b', pid=200)
    path = items['ALGO02/worker/read_receipts/201.json']['path']
    data = json.loads(path.read_text())
    data['read_paths'] = ['/b/another-satellite.json']
    path.write_text(json.dumps(data))
    b, _ = audit_catalogue(items)
    assert all(a[k]['forest_sha256'] != b[k]['forest_sha256'] for k in a)


def test_cyclic_read_dependencies_are_rejected(tmp_path):
    items = catalogue(tmp_path)
    path = items['ALGO02/worker/read_receipts/100.json']['path']
    data = json.loads(path.read_text())
    data['read_paths'] = ['/a/ALGO03/read_receipts/110.json']
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Cyclic dependency'):
        audit_catalogue(items)


@pytest.mark.parametrize('bad', [0, None, {}, ''])
def test_denied_paths_requires_explicit_empty_list(bad):
    rows = records()
    rows[0][1]['denied_paths'] = bad
    with pytest.raises(ValueError, match='denied read'):
        audit_group(rows, store_root='/a')


def test_duplicate_read_paths_are_rejected():
    rows = records()
    rows[0][1]['read_paths'] *= 2
    with pytest.raises(ValueError, match='sorted unique'):
        audit_group(rows, store_root='/a')


def test_duplicate_source_receipt_paths_are_rejected(tmp_path):
    items = catalogue(tmp_path)
    rows = list(items.values())
    rows[1]['source_path'] = rows[0]['source_path']
    with pytest.raises(ValueError, match='Duplicate source'):
        audit_catalogue(items)
