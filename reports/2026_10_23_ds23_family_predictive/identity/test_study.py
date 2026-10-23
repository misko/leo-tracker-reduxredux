from pathlib import Path
import json
import numpy as np
from study import union_keep

def test_union_mask_withholds_original_and_replacement_rows():
    from types import SimpleNamespace
    p=SimpleNamespace(keep=np.array([1,1,1,0,1],bool),rows=[dict(candidate_index=j) for j in [1,2,3]],slices=[slice(0,2),slice(2,4),slice(4,5)])
    assert union_keep(p,{1,2}).tolist()==[False,False,False,False,True]
    assert p.keep.tolist()==[True,True,True,False,True]

def test_complete_matched_masks_and_fresh_symmetric_physical_priors():
    root=Path(__file__).parent
    for family in [65340,67618]:
        rows=[json.loads((root/f'{family}_{arm}_{position}.json').read_text()) for arm in ['c0','fitted_c'] for position in ['graph_parent','native_RF_endpoint']]
        for d in rows:
            assert d['status']=='complete' and d['calibration_phase_converged']
            assert d['held_fit_ID_overlap']==0 and not set(d['calibration_IDs'])&set(d['held_observation_ids'])
            assert d['all_shortlist_family_curved_points_withheld'] and d['coarse_catalogue_count']==1338
            assert d['calibration_IDs']==rows[0]['calibration_IDs']
            assert d['held_observation_ids']==rows[0]['held_observation_ids']
            assert d['candidate_norads']==rows[0]['candidate_norads']
            ng=len(d['members'])
            for c in d['candidates']:
                assert c['phase_and_modes_never_reuse_calibration'] and c['physical_modes']
                mean=np.array(c['prior_mean']);cov=np.array(c['prior_covariance']);nb=len(mean)-4-ng
                assert mean[nb]==c['phase_prior_mean_s']/c['phase_prior_width_s']
                np.testing.assert_array_equal(mean[nb+1:nb+4],np.zeros(3))
                np.testing.assert_array_equal(cov[nb:nb+4,nb:nb+4],np.eye(4))
                np.testing.assert_array_equal(cov[:nb,nb:],np.zeros((nb,4+ng)))

def test_frozen_protocol_inputs_and_source_hashes():
    import hashlib
    p=json.loads((Path(__file__).parent/'protocol.json').read_text())
    for path,expected in p['input_hashes'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==expected
    assert hashlib.sha256((Path(__file__).parent/'study.py').read_bytes()).hexdigest()==p['source_sha256']
