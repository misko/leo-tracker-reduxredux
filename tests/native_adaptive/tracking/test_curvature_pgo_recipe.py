from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tools'))
from build_curvature_pgo import commands


def test_profile_generation_and_use_share_object_identity():
    root=Path('/var/tmp/example')
    generated=commands(root,'generate','compiler');used=commands(root,'use','compiler')
    assert [x[x.index('-o')+1] for x in generated[:-1]]==[x[x.index('-o')+1] for x in used[:-1]]
    assert all('-fprofile-generate' in x and '-fprofile-update=atomic' in x for x in generated)
    assert all('-fprofile-use' in x and '-Werror=coverage-mismatch' in x for x in used)
    assert all('-fno-fast-math' in x and '-ffp-contract=off' in x for x in generated+used)
    assert all(not any('no-error' in flag or 'profile-correction' in flag for flag in x) for x in used)


def test_invalid_mode_fails_before_build():
    with pytest.raises(ValueError):commands(Path('/var/tmp/example'),'typo','compiler')


def test_grid_component_uses_its_own_profile_objects():
    recipes=commands(Path('/var/tmp/example'),'use','compiler','grid')
    assert [Path(c[c.index('-o')+1]).name for c in recipes[:-1]]==['tracking.o','grid_trial.o']
    with pytest.raises(ValueError):commands(Path('/var/tmp/example'),'use','compiler','typo')
