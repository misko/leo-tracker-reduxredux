from copy import deepcopy

import pytest
from compare_algo07v3_annotation import compare


def test_annotation_comparator_checks_intermediate_predictions_and_prefix():
    reference = dict(result=dict(annotation='unchanged'),nominations={'1':[123,456]},
                     attempts={'1':dict(variance=123.)})
    prefix = dict(recovery_inventory={'owner':'original'})
    candidate = dict(prefix,predictive_annotation=deepcopy(reference))
    assert compare(reference,candidate,prefix)['exact']
    candidate['predictive_annotation']['attempts']['1']['variance'] = 124.
    with pytest.raises(ValueError,match='attempts'):
        compare(reference,candidate,prefix)
    candidate['predictive_annotation'] = reference
    with pytest.raises(ValueError,match='scientific prefix changed'):
        compare(reference,candidate,dict(recovery_inventory={'owner':'changed'}))
