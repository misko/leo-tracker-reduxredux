from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
    return import_module("primary_anchor_8ms")


def test_recipe_binds_first_scan_in_separate_identity(adapter):
    ordinary = {"aperture_samples":[200_000,80_000]}
    recipe = dict(ordinary, **{adapter.RECIPE_FIELD:adapter.definition()})
    assert adapter.single_anchor_options(recipe)==ordinary
    assert adapter.RECIPE_FIELD in recipe
    recipe[adapter.RECIPE_FIELD]["symbol"] = "cancellation_factors"
    with pytest.raises(ValueError,match="Unrecognized"):
        adapter.single_anchor_options(recipe)


def test_only_full_anchor_gets_first_scan_and_scope_restores_factory(adapter, monkeypatch):
    old = SimpleNamespace(argtypes=(int,), restype=int)
    helper = SimpleNamespace()
    factory = lambda *_args: SimpleNamespace(call=old,maximum=2)
    monkeypatch.setattr(adapter.mixed,"NativePath",factory)

    @contextmanager
    def generic(*_args):
        full = adapter.mixed.NativePath(None,None,"full")
        short = adapter.mixed.NativePath(None,None,"short_primary")
        yield full,short

    monkeypatch.setattr(adapter.mixed.MixedApertureDetector,"detector",generic)
    mixer = adapter.AnchorPrimaryMixer(Path(__file__),"test",helper)
    with mixer.detector() as (full,short):
        assert (full.call,full.maximum)==(helper,1)
        assert (short.call,short.maximum)==(old,2)
        assert adapter.mixed.NativePath is factory


def test_comparison_includes_empty_residual_only_and_every_rank_zero_field(adapter):
    trial = import_module("primary_anchor_8ms_trial")
    zero = (0,12,.25,-300_012.,.125,.04)
    residual = (1,18,.5,650_000.,.3,.08)
    assert trial.verified_rank_zero((zero,residual),(zero,))
    assert trial.verified_rank_zero((residual,),())
    assert not trial.verified_rank_zero((zero,),((0,*zero[1:-1],.05),))
