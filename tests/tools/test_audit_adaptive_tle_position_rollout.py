from __future__ import annotations

import importlib.util
import json
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from leo.storage.adaptive_tle_position import AdaptiveTlePositionStore
from tests.contracts.test_adaptive_tle_position import document


def _subject():
    path = Path(__file__).parents[2] / "tools/audit_adaptive_tle_position_rollout.py"
    spec = importlib.util.spec_from_file_location("audit_adaptive_tle_position_rollout", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _png() -> bytes:
    image = Image.new("RGB", (4, 3), "navy")
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_audit_verifies_public_document_png_and_fixed_mask_evidence(tmp_path, monkeypatch) -> None:
    subject = _subject()
    diagnostic = document().model_copy(
        update={
            "diagnostics": {
                "reference_evaluation_only": {"used_for_inference": False},
                "track_evidence": [
                    {
                        "track_id": "track-1",
                        "observation_ids": ["a", "b", "c", "d", "e", "f"],
                        "times_s": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
                        "training_mask": [True, False, True, False, True, False],
                        "partition_seed": "sha256:" + "a" * 64,
                    }
                ],
            }
        }
    )
    writer = AdaptiveTlePositionStore(tmp_path, read_only=False)
    image = _png()
    manifest = writer.publish(diagnostic, image)
    inventory = {
        "frozen_window": {"start_utc_ns": 1, "end_utc_ns": 2},
        "session_ids_newest_first": ["scan-1", "scan-pending"],
    }

    class Inputs:
        def load(self, session_id):
            assert session_id == "scan-1"
            return SimpleNamespace(
                input_manifest_sha256=diagnostic.input_manifest_sha256,
                analysis_manifest_sha256=diagnostic.analysis_manifest_sha256,
            )

    def fake_http_get(url, _timeout):
        if url == "http://api.test/api/v1/scanner/tracking/scan-1/adaptive-tle-position":
            return json.dumps(
                {
                    "session_id": "scan-1",
                    "state": "complete",
                    "manifest": {
                        "document_sha256": manifest.document_sha256,
                        "artifacts": [{"name": "map", "sha256": manifest.artifacts[0].sha256}],
                    },
                }
            ).encode()
        assert "map.png?sha256=" in url
        return image

    monkeypatch.setattr(subject, "_http_get", fake_http_get)
    receipt = subject.audit_rollout(
        AdaptiveTlePositionStore(tmp_path),
        inventory,
        tracking_inputs=Inputs(),
        api_base="http://api.test",
    )

    assert receipt["summary"]["frozen_session_count"] == 2
    assert receipt["summary"]["publication_states"] == {
        "pending": 1,
        "diagnostic": 1,
        "insufficient": 0,
        "failed": 0,
    }
    assert receipt["summary"]["verified_map_png_count"] == 1
    assert receipt["summary"]["verified_api_route_count"] == 1
    assert receipt["summary"]["current_source_manifest_match_count"] == 1
    assert receipt["summary"]["invalid_publication_count"] == 0
    assert receipt["summary"]["diagnostic_fixed_split_totals"] == {
        "tracks": 1,
        "observations": 6,
        "training_observations": 3,
        "heldout_observations": 3,
        "partition_seeds": 1,
    }
    assert receipt["sessions"][0]["map_size_px"] == [4, 3]
    assert receipt["sessions"][0]["valid"] is True
    assert receipt["sessions"][0]["api_verified"] is True
    assert receipt["sessions"][0]["current_source_manifest_match"] is True
    assert receipt["sessions"][1] == {
        "session_id": "scan-pending",
        "publication_state": "pending",
    }
