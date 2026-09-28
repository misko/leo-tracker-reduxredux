from types import SimpleNamespace
import importlib.util
from pathlib import Path

import numpy as np
import pytest

# Avoid colliding with another research report's run_prototype module when
# both component suites are collected in one pytest process.
_spec = importlib.util.spec_from_file_location("joint_location_runner", Path(__file__).with_name("run_prototype.py"))
_runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_runner)
load_document, point_factory = _runner.load_document, _runner.point_factory


class Document:
    def model_dump(self, mode):
        assert mode == "json"
        return {"session_id":"scan-fw-test"}


def test_public_store_adapter_fails_closed_when_missing():
    store=SimpleNamespace(status=lambda sid: SimpleNamespace(manifest=None))
    with pytest.raises(ValueError,match="absent"):
        load_document(store,"scan-fw-test")


def test_public_store_adapter_returns_verified_manifest_document():
    manifest=SimpleNamespace(document=Document(),document_sha256="sha256:abc")
    store=SimpleNamespace(status=lambda sid: SimpleNamespace(manifest=manifest))
    assert load_document(store,"scan-fw-test")==({"session_id":"scan-fw-test"},"sha256:abc")


def test_public_store_adapter_propagates_tamper_failure():
    def tampered(_sid):
        raise ValueError("adaptive TLE position document digest differs")
    with pytest.raises(ValueError,match="digest differs"):
        load_document(SimpleNamespace(status=tampered),"scan-fw-test")


def test_local_point_factory_matches_geodetic_shape_and_unit_up():
    point=point_factory(37.8,-122.4)(12.5,-12.5)
    assert point.ecef_km.shape==(3,)
    assert np.linalg.norm(point.up)==pytest.approx(1.0)
