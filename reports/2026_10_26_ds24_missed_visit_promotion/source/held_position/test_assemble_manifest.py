import pytest
from assemble_manifest import index_unique

def test_duplicate_case_variant_cannot_inflate_coverage():
    row=dict(case='case',variant='baseline')
    with pytest.raises(ValueError):index_unique([row,row])

def test_distinct_variant_remains_separate():
    assert len(index_unique([dict(case='case',variant='baseline'),dict(case='case',variant='additions_bin_floor')]))==2
