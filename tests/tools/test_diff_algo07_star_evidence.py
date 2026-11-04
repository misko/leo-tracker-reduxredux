from diff_algo07_star_evidence import differences, normalized


def test_scientific_values_and_operational_values_are_both_reported():
    left = dict(owner=123, alias=0, gate=True, objective=4., seconds=1., x=[0., 1.])
    right = dict(owner=124, alias=1, gate=False, objective=5., seconds=2., x=[0., 2.])
    assert {r['path'] for r in differences(left, right)} == {
        '/owner', '/alias', '/gate', '/objective', '/seconds', '/x/1'}


def test_signed_zero_and_numeric_type_changes_are_visible():
    assert list(differences(0., -0.))[0]['kind'] == 'float'
    assert list(differences(1, 1.))[0]['kind'] == 'type'


def test_only_declared_path_prefix_is_normalized():
    value = dict(source='/private/file.json', comment='about /private/file.json',
                 outside='/private-other/file.json')
    result = normalized(value, '/private')
    assert result['source'] == '<PRIVATE_STORE>/file.json'
    assert result['comment'] == value['comment']
    assert result['outside'] == value['outside']
