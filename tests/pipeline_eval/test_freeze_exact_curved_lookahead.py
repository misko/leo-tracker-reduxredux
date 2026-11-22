import os
from importlib import import_module
from types import SimpleNamespace

import pytest

from leo.storage.fast_scan import FastSegmentSource
from tools.pipeline_eval.qualification import experimental_publication as publication

FREEZER = import_module("reports.ALGO08.single-core-2x.freeze_exact_curved_lookahead")


def test_member_lookahead_disabled_by_default_and_requires_paired_ingress():
    enabled = publication._member_lookahead_enabled
    assert enabled({"ingress": "paired-sha256"}) is False
    assert enabled({"ingress": "stock", "member_lookahead": False}) is False
    assert enabled({"ingress": "paired-sha256", "member_lookahead": True}) is True
    with pytest.raises(ValueError, match="paired SHA-256"):
        enabled({"ingress": "compressed-buffer", "member_lookahead": True})
    with pytest.raises(ValueError, match="Boolean"):
        enabled({"ingress": "paired-sha256", "member_lookahead": "true"})


def test_member_lookahead_checks_the_bundle_file_content_and_manifest(tmp_path, monkeypatch):
    root = tmp_path / "bundle"
    destination = root / publication.MEMBER_LOOKAHEAD_SOURCE
    destination.parent.mkdir(parents=True)
    original = publication._checked_member_lookahead
    pins = {"sources": {str(publication.MEMBER_LOOKAHEAD_SOURCE):
                        publication.MEMBER_LOOKAHEAD_SHA256}}
    assert original(pins).__name__ == "compressed_member_lookahead"
    with pytest.raises(ValueError, match="reviewed source"):
        original({"sources": {}})
    monkeypatch.setattr(publication, "__file__",
                        str(root / "tools/pipeline_eval/qualification/experimental_publication.py"))
    monkeypatch.setattr(publication.util, "find_spec",
                        lambda name: SimpleNamespace(origin=str(destination)))
    destination.write_text("Different file content\n")
    with pytest.raises(ValueError, match="reviewed source"):
        original(pins)


@pytest.mark.parametrize("missing", ("posix_fadvise", "POSIX_FADV_WILLNEED"))
def test_unsupported_advice_leaves_serial_acquisition_untouched(missing, monkeypatch):
    shim = import_module(publication.MEMBER_LOOKAHEAD_MODULE)
    monkeypatch.delattr(os, missing, raising=False)
    before = FastSegmentSource.windows
    counts = {}

    def acquire(value):
        assert FastSegmentSource.windows is before
        return value

    scoped = publication._with_member_lookahead(acquire, shim.compressed_member_lookahead, counts)
    assert not counts
    value = object()
    assert scoped(value) is value
    assert FastSegmentSource.windows is before
    assert counts == dict(attempts=0, submitted=0, submitted_bytes=0, cpu_ns=0, wall_ns=0)


def test_freezer_authenticates_independent_ingress_and_detector_evidence(tmp_path):
    hasher = "cb8a3f9f88e608a04744c7776c22cb5d31b063e43cd1af657951b90adfe3e933"
    FREEZER.verify_receiver_transfer(FREEZER.TRANSFER)
    FREEZER.verify_ingress_trial(FREEZER.INGRESS, hasher)
    with pytest.raises(ValueError, match="paired ingress"):
        FREEZER.verify_ingress_trial(FREEZER.INGRESS, "0" * 64)
    changed = tmp_path / "receiver.json"
    changed.write_bytes(FREEZER.TRANSFER.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="reviewed comparison"):
        FREEZER.verify_receiver_transfer(changed)
