"""Owned fixed-prior path is the exact measured prototype; original oracle is frozen."""

import ast
import hashlib
import inspect
from pathlib import Path

import algo07v3_prefixed_prior_oracle as reference
from probe_algo07v3_fixed_priors import candidate

from leo.analysis.localization_v3 import hierarchical


def test_baseline_snapshot_preserves_original_qualified_bytes():
    assert hashlib.sha256(Path(reference.__file__).read_bytes()).hexdigest() == (
        'c906a5992ca3428c29b5c44326264549e18dc4206653b3d6f2fd12b48638607e')


def test_owned_body_matches_exact_fixed_prior_prototype():
    _, _, source = candidate()
    assert ast.dump(ast.parse(inspect.getsource(hierarchical.hierarchical_bound))) == (
        ast.dump(ast.parse(source)))
