import numpy as np
from inventory_joint_attachment_validation import eligible, identity
from stress_joint_attachment import inject


def test_inventory_excludes_any_owned_point_and_requires_overlap():
    def track(ch,start):
        return dict(key=str(ch),channel=ch,receiver=1,times=list(np.linspace(start,start+30,25)),
                    observation_ids=[f'{ch}:{i}' for i in range(25)])
    tracks=[track(7,0),track(8,5)]
    assert len(eligible(tracks,set())['pairs'])==1
    assert not eligible(tracks,{'7:3'})['pairs']
    assert not eligible([track(7,0),track(8,25)],set())['pairs']
    assert identity({'session_id':'new-name','raw_recording_authority_digest':'raw'}) & identity({'session_id':'old-name','raw_recording_authority_digest':'raw'})


def test_known_origin_controls_reproducible_and_paired_noise():
    times=np.tile(np.linspace(0,60,31),2);owners=np.repeat([0,1],31)
    mean=times*2;alternate=mean+100+times*3
    y,correct=inject(mean,alternate,times,owners,'correct',4081)
    split,truth=inject(mean,alternate,times,owners,'split_identity',4081)
    np.testing.assert_allclose(truth['noise_hz'],correct['noise_hz'])
    np.testing.assert_allclose((split-y)[owners==0],0)
    np.testing.assert_allclose((split-y)[owners==1],(alternate-mean)[owners==1])
    assert set(truth['labels'][owners==1])=={58101}
    _,joined=inject(mean,alternate,times,owners,'joined_identity',4081)
    assert set(joined['labels'])=={57701,58101}
    # Continuous mean at the seam even though the physical identity switches.
    np.testing.assert_allclose(joined['mean_hz'][times==30],mean[times==30])
