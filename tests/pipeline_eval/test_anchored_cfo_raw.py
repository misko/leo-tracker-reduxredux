from hashlib import sha256
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def entry(monkeypatch):
    here = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    monkeypatch.syspath_prepend(str(here))
    return importlib.import_module("anchored_cfo_raw")


def test_pack_binds_source_binary_and_guard_metadata(tmp_path, monkeypatch, entry):
    source, library = b"reviewed native source", b"reviewed detector"
    monkeypatch.setattr(entry, "HERE", tmp_path)
    monkeypatch.setattr(entry, "SOURCES", {"reviewed.inc": sha256(source).hexdigest()})
    monkeypatch.setattr(entry, "LIBRARIES", {"detector.so": sha256(library).hexdigest()})
    (tmp_path / "reviewed.inc").write_bytes(source)
    (tmp_path / "detector.so").write_bytes(library)
    package = tmp_path / "pack.json"
    original = entry.specification()
    package.write_text(json.dumps(original))
    assert entry.verified_pack(tmp_path) == {"detector.so": tmp_path / "detector.so"}

    package.write_text(json.dumps(original | {"guards": original["guards"] | {"anchor_stride": 64}}))
    with pytest.raises(ValueError, match="reviewed recipe"):
        entry.verified_pack(tmp_path)
    package.write_text(json.dumps(original))
    (tmp_path / "detector.so").write_bytes(library+b"!")
    with pytest.raises(ValueError, match="artifact differs"):
        entry.verified_pack(tmp_path)
    (tmp_path / "detector.so").write_bytes(library)
    (tmp_path / "reviewed.inc").write_bytes(source+b"!")
    with pytest.raises(ValueError, match="artifact differs"):
        entry.verified_pack(tmp_path)


@pytest.mark.parametrize("sign", (-1, 1))
def test_alias_collar_reuses_exact_gather_and_original_publication_fields(entry, sign):
    from reports.ALGO08.v3.short_cfo_refine import amend

    factor = dict(zip(entry.exact.FIELDS, (0, 12, -.375, sign*799_990., .58, .05), strict=True))
    factor.update(passed_fractional_margin_gate=True, fractional_margin=.53)
    original = dict(candidates=[factor], receiver_id=1, valid_start_counter=81)
    rest = (0., 0., .99, .99, .69, .12, 5.)
    calls = []

    def fallback(*args):
        calls.append(args[2])
        return (sign*9.9, *rest)

    policy = SimpleNamespace(amend=amend, band_retries=0,
        refiner=SimpleNamespace(diagnostics=lambda *args: (sign*10.0005, *rest)),
        exact_gather=SimpleNamespace(diagnostics=fallback))
    after, decision, changed = entry.guarded_probe(original, None, None, policy, 0.)
    assert decision == "updated" and changed
    assert calls == [1] and policy.band_retries == 1
    assert after == dict(original, candidates=[dict(factor, **{entry.exact.CFO: sign*799_999.9})])
    assert factor[entry.exact.CFO] == sign*799_990.


def test_distinct_guarded_recipe_preserves_original_fixed_timing_and_named_parent(entry):
    parent, source = "1"*64, dict(rule=["full", "short_primary"], aperture_samples=[200000, 120000])
    baseline = entry.exact.recipe(source, parent)
    guarded = entry.recipe(source, parent)
    assert {k: v for k, v in guarded.items() if k != "guarded_phase"} == baseline
    assert guarded["guarded_phase"]["libraries"] == entry.LIBRARIES
    assert guarded["guarded_phase"]["guards"]["tail_step"] == 1.0
    assert entry.exact.recipe(source, parent) == baseline
