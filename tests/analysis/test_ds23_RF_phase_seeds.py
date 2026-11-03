import numpy as np
from ds23_RF_phase_seeds import seed_vectors


def group(name,phase=2.,gap=20.,other_phase=999.):
    candidates=[dict(first_index=1,second_index=2,phase_first_s=phase,phase_second_s=-phase,score=0.,
        relative_residual_noise=dict(noise_screen_pass=True)),dict(score=gap)]
    return dict(group=name,results=dict(regional_centre=dict(candidates=candidates),
        current_scan_RF_mode=dict(candidates=[dict(phase_first_s=other_phase)])))


def test_RF_mode_and_unretained_identities_do_not_enter_seed():
    r=seed_vectors([1,4],[.1,.2],[group('a')])
    np.testing.assert_array_equal(r['RF_median'],[2.,0.])
    np.testing.assert_array_equal(r['RF_consensus'],[0.,0.])
    np.testing.assert_array_equal(r['prior_mean'],[.1,.2])


def test_local_pool_ambiguity_filter_precedes_proposals():
    r=seed_vectors([1,2],[0.,0.],[group('a',gap=1.)])
    np.testing.assert_array_equal(r['RF_median'],[0.,0.])


def test_consensus_requires_distinct_coherent_groups():
    r=seed_vectors([1,2],[0.,0.],[group('a',phase=2.),group('b',phase=2.2)])
    np.testing.assert_allclose(r['RF_consensus'],[2.1,-2.1])
    r=seed_vectors([1,2],[0.,0.],[group('a',phase=2.),group('a',phase=2.2)])
    np.testing.assert_array_equal(r['RF_consensus'],[0.,0.])
    r=seed_vectors([1,2],[0.,0.],[group('a',phase=2.),group('b',phase=4.)])
    np.testing.assert_array_equal(r['RF_consensus'],[0.,0.])
