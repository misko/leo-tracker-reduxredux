from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_PATH = Path(__file__).with_name("status_snapshot.py")
_SPEC = importlib.util.spec_from_file_location("ds2_status", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(MODULE)


def test_status_keeps_only_the_sealed_tracking_summary(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "state": "complete",
                    "phase": "complete",
                    "product": {
                        "schema_version": 14,
                        "analysis_id": "scanner-shared-tracking-v14",
                        "input_manifest_sha256": "sha256:input",
                        "analysis_manifest_sha256": "sha256:analysis",
                        "configuration_digest": "sha256:configuration",
                        "tracklets": [{}, {}],
                        "tle_candidates": [{}],
                        "review_count": 1,
                        "artifacts": [{}, {}, {}],
                    },
                }
            ).encode()

    monkeypatch.setattr(MODULE, "urlopen", lambda *_args, **_kwargs: Response())
    value = MODULE.status("scan-fw-0123456789abcdef")
    assert value["state"] == "complete"
    assert value["tracking"] == {
        "schema_version": 14,
        "analysis_id": "scanner-shared-tracking-v14",
        "input_manifest_sha256": "sha256:input",
        "analysis_manifest_sha256": "sha256:analysis",
        "configuration_digest": "sha256:configuration",
        "tracklet_count": 2,
        "tle_candidate_count": 1,
        "review_count": 1,
        "artifact_count": 3,
    }
