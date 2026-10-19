import importlib.util
from pathlib import Path
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('fixed_confidence',ROOT/'tools/probe_ds23_fixed_confidence.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_confidence_does_not_upweight_ambiguous_evidence():
    result=module.confidence_controls([0,.5,1],[1,.6,.2])
    np.testing.assert_allclose(result['support_confidence'],[.05,.315,.2])
    np.testing.assert_allclose(result['confidence_only'],[.05,.5,1])
    np.testing.assert_array_equal(result['unit'],[1,1,1])


@pytest.mark.parametrize('confidence,support',[([np.nan],[1]),([1.1],[1]),([.5],[0]),([.5],[1,1])])
def test_invalid_weights_rejected(confidence,support):
    with pytest.raises(ValueError):module.confidence_controls(confidence,support)
