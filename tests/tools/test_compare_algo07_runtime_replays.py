import json

from compare_algo07_runtime_replays import compare


def test_changed_screen_rejected_even_with_same_fallback_endpoint(tmp_path):
    a, b = tmp_path/'a', tmp_path/'b'
    for root in (a, b):
        (root/'SCAN').mkdir(parents=True)
        (root/'SCAN/result.json').write_text(json.dumps(dict(
            selected=None, final=dict(x=[1., 2.]), screen=dict(passes=True))))
    assert compare(a, b)['passed']
    value = json.loads((b/'SCAN/result.json').read_text())
    value['screen']['passes'] = False
    (b/'SCAN/result.json').write_text(json.dumps(value))
    assert not compare(a, b)['passed']
    value['screen']['passes'] = True
    value['final']['x'][0] += .001
    (b/'SCAN/result.json').write_text(json.dumps(value))
    assert not compare(a, b)['passed']
