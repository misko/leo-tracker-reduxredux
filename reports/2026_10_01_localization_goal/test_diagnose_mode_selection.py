from diagnose_mode_selection import describe


def test_reference_diagnostic_does_not_replace_likelihood_winner():
    winner = dict(seed_index=0, mean=[5., 0.], objectives=[1.], converged=True)
    alternate = dict(seed_index=1, mean=[1., 0.], objectives=[4.], converged=True)
    unfinished = dict(seed_index=2, mean=[0., 0.], objectives=[6.], converged=False)
    receipt = dict(best=winner, fits=[winner, alternate, unfinished])
    result = describe(receipt, lambda point: point[0]*1000)
    assert result['winner']['seed_index'] == 0
    assert result['reference_best_sampled_mode']['seed_index'] == 1
    assert result['reference_best_sampled_mode']['objective_gap'] == 3
    assert result['sampled_alternative_within_3km']
    assert len(result['modes']) == 2
    assert receipt['best'] is winner


def test_sampled_modes_all_bad_is_not_a_global_search_claim():
    winner = dict(seed_index=0, mean=[5., 0.], objectives=[1.], converged=True)
    result = describe(dict(best=winner, fits=[winner]), lambda p: p[0]*1000)
    assert result['winner_over_3km']
    assert not result['sampled_alternative_within_3km']
