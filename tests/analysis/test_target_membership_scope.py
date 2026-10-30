import pytest
from audit_target_membership_scope import scoped_membership


def test_unscored_discoveries_remain_explicit_without_becoming_validated_points():
    args=({'old'},{'old','target','extra'},{'target'},{'old','target'},{'old':1},{'old':1,'target':2,'extra':3})
    r=scoped_membership(*args)
    assert r['reviewed_associated_ids']==['old','target']
    assert r['incidental_unvalidated_ids']==['extra']
    bad=list(args);bad[3]={'old','target','extra'}
    with pytest.raises(ValueError,match='fitted observations'):scoped_membership(*bad)
    bad=list(args);bad[5]={'old':9,'target':2,'extra':3}
    with pytest.raises(ValueError,match='owner changed'):scoped_membership(*bad)
