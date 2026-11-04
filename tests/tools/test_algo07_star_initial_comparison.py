from compare_algo07_star_initial import compare_preparation


def test_preparation_comparison_detects_changes_to_each_input(tmp_path, monkeypatch):
    names = ('tracks.json', 'owners.json', 'causal.tle', 'aliases.json', 'bank.npz')
    monkeypatch.setattr('compare_algo07_star_initial.INPUTS', names)
    roots = [tmp_path/'reference', tmp_path/'candidate']
    for root in roots:
        root.mkdir()
        for name in names:
            (root/name).write_bytes(b'original')
    assert compare_preparation(*roots)['exact']
    for name in names:
        (roots[1]/name).write_bytes(b'changed')
        result = compare_preparation(*roots)
        assert not result['exact']
        differences = [r['path'] for r in result['files']
                       if r['reference_sha256'] != r['candidate_sha256']]
        assert differences == [name]
        (roots[1]/name).write_bytes(b'original')
