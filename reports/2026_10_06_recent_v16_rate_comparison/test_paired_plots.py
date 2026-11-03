import pytest
from paired_plots import matched


def test_pairs_hold_every_other_switch_fixed_and_require_completed_results():
    a=dict(scan='a',refinement='original',model='V16',cone='off',arm='fitted-c',status='complete')
    b=dict(a,refinement='refined')
    rows=[a,b,dict(a,scan='b'),dict(b,scan='b',status='pending'),
          dict(b,cone='on'),dict(b,arm='zero-c')]
    assert matched(rows,'refinement','original','refined',dict(model='V16',cone='off',arm='fitted-c'))==[(a,b)]
    with pytest.raises(ValueError):matched([a,a,b],'refinement','original','refined',{})
