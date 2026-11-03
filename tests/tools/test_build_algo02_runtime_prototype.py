"""The ALGO02 optimization must preserve its earlier scientific API."""

import argparse
import json

import build_algo02_runtime_prototype as builder
import pytest
from build_algo02_runtime_prototype import adapt_helper


def test_adaptation_preserves_older_policy_and_api():
    source = ('def make_problem(scan,node,keep,arm,reference,weights,means,multiplier,nu):\n'
              '    result=JointMarginal.calculate(p,x)\n'
              '    return result\n')
    changed = adapt_helper(source)
    assert changed.replace(',geometry_only=True', '') == source
    assert 'support_policy' not in changed


@pytest.mark.parametrize('source', ['', 'result=JointMarginal.calculate(p,x)' * 2,
                                    'result=JointMarginal.calculate(p,x,geometry_only=True)'])
def test_rejects_unexpected_or_already_changed_helper(source):
    with pytest.raises(ValueError):
        adapt_helper(source)


def test_manifest_tampering_rejected_before_output_creation(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "release-manifest.json").write_text(json.dumps({"revision": builder.BASELINE}))
    with pytest.raises(ValueError, match="manifest differs"):
        builder.build(argparse.Namespace(source=source, checkout=tmp_path,
            output=builder.Path('/srv/bulk/leo/research/nonexistent-test-output')))
