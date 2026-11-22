from contextlib import contextmanager
from hashlib import sha256
from importlib import import_module
from types import SimpleNamespace

import pytest

from tools.pipeline_eval.qualification import experimental_publication as publication

FREEZER = import_module("reports.ALGO08.single-core-2x.freeze_curved_design")


def test_bundle_hook_requires_the_exact_measured_overlay(monkeypatch):
    source = str(publication.CURVED_DESIGN_SOURCE)
    pins = {"sources": {source: publication.CURVED_DESIGN_SHA256}}
    measure = publication._checked_curved_design(pins)
    assert measure.__name__ == "measured_curved_design"

    with pytest.raises(ValueError, match="measured source"):
        publication._checked_curved_design({"sources": {source: "0" * 64}})
    discover = publication.util.find_spec
    monkeypatch.setattr(publication.util, "find_spec", lambda name: (
        SimpleNamespace(origin="/different/unchecked.py")
        if name == publication.CURVED_DESIGN_MODULE else discover(name)
    ))
    with pytest.raises(ValueError, match="measured source"):
        publication._checked_curved_design(pins)


def test_curved_design_only_applies_inside_the_solver_callback():
    active = False

    @contextmanager
    def measure(*, enabled):
        nonlocal active
        active = enabled
        try:
            yield {"direct_assembly_calls": 3}
        finally:
            active = False

    def solve(offer):
        assert active
        return offer

    counts = {}
    scoped = publication._with_curved_design(solve, measure, counts)
    assert not active and not counts
    offer = object()
    assert scoped(offer) is offer
    assert counts == {"direct_assembly_calls": 3}
    assert not active


def test_saved_scientific_evidence_rejects_changed_bytes(tmp_path):
    FREEZER.verify_saved_solves(FREEZER.SAVED_SOLVES)
    changed = tmp_path / "trial.json"
    changed.write_bytes(FREEZER.SAVED_SOLVES.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="reviewed comparison"):
        FREEZER.verify_saved_solves(changed)


def test_inherited_libraries_relocate_without_changing_binary_pin(tmp_path):
    parent, output = tmp_path / "parent", tmp_path / "new"
    parent.mkdir()
    library = parent / "path.so"
    library.write_bytes(b"pinned library")
    digest = sha256(library.read_bytes()).hexdigest()
    spec = {"graph_path": {"library": str(library), "sha256": digest},
            "sources": {library.name: digest}}
    assert FREEZER.relocate_libraries(parent, output, spec) == {
        "graph_path": {"library": str(output / library.name), "sha256": digest},
    }
    library.write_bytes(b"different library")
    with pytest.raises(ValueError, match="Inherited library differs"):
        FREEZER.relocate_libraries(parent, output, spec)
