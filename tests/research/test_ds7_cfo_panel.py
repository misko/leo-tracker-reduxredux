from __future__ import annotations

import copy

import pytest

from tools.ds7_cfo_panel import build_api_inventory, freeze_panel, validate_matched_epochs


def _documents():
    captures = []
    rows = []
    classes = ["strong", "weak", "failed", "strong"]
    for index, rate in enumerate((2_500_000, 5_000_000, 7_500_000, 10_000_000)):
        session = f"scan-fw-{index}"
        digest = f"sha256:{index:064x}"
        captures.append(
            {"session_id": session, "manifest_sha256": digest, "sample_rate_hz": rate}
        )
        rows.append(
            {
                "session_id": session,
                "manifest_sha256": digest,
                "sample_rate_hz": rate,
                "support_class": classes[index],
                "receiver_ids": [0, 1],
                "tracking_state": "complete" if classes[index] != "failed" else "failed",
                "tracklet_count": 10 - index,
            }
        )
    plan = {
        "dataset_sha256": "sha256:" + "a" * 64,
        "content_sha256": "sha256:" + "b" * 64,
        "captures": captures,
    }
    inventory = {
        "schema": "ds7-cfo-support-inventory/v1",
        "dataset_sha256": plan["dataset_sha256"],
        "reference_audit": "reference_excluded",
        "source": {"port": "public_observation_product", "endpoint": "fixture"},
        "rows": rows,
    }
    return plan, inventory


def test_freezes_four_rate_support_balanced_panel_without_iq():
    plan, inventory = _documents()
    panel = freeze_panel(plan, inventory)
    assert {row["sample_rate_hz"] for row in panel["captures"]} == {
        2_500_000,
        5_000_000,
        7_500_000,
        10_000_000,
    }
    assert {row["support_class"] for row in panel["captures"]} == {
        "strong",
        "weak",
        "failed",
    }
    assert panel["execution"]["raw_iq_read_bytes"] == 0
    assert panel["native_waveform_applicability"]["full_band_waveform"]["eligible"] is False


def test_rejects_reference_bearing_fields_before_selection():
    plan, inventory = _documents()
    inventory["rows"][0]["observer_site"] = {"latitude": 1.0}
    with pytest.raises(ValueError, match="reference-bearing"):
        freeze_panel(plan, inventory)


def test_rejects_non_allowlisted_product_fields():
    plan, inventory = _documents()
    inventory["rows"][0]["quality_scores"] = [0.9]
    with pytest.raises(ValueError, match="non-allowlisted"):
        freeze_panel(plan, inventory)


def test_matched_epoch_adapter_requires_all_methods_even_on_failure():
    document = {
        "schema": "ds7-cfo-matched-epochs/v1",
        "methods": ["baseline", "robust_profile"],
        "rows": [
            {
                "session_id": "s",
                "receiver_id": 0,
                "epoch_utc_ns": 1,
                "method": "baseline",
                "status": "supported",
            },
            {
                "session_id": "s",
                "receiver_id": 0,
                "epoch_utc_ns": 1,
                "method": "robust_profile",
                "status": "rejected",
            },
        ],
    }
    validate_matched_epochs(document)
    broken = copy.deepcopy(document)
    broken["rows"].pop()
    with pytest.raises(ValueError, match="every matched epoch"):
        validate_matched_epochs(broken)


def test_api_inventory_projects_only_public_support_metadata(monkeypatch):
    plan, _ = _documents()

    class Response:
        def __init__(self, capture):
            self.capture = capture

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            product = {
                "schema_version": 14,
                "input_manifest_sha256": self.capture["manifest_sha256"],
                "analysis_manifest_sha256": "sha256:" + "c" * 64,
                "attempted_group_count": 4,
                "deferred_group_count": 2,
                "tracklets": [{"receiver_id": index % 2} for index in range(8)],
                "observer_site": {"opaque": "must not be projected"},
            }
            return __import__("json").dumps(
                {"state": "complete", "failure_summary": None, "product": product}
            ).encode()

    captures = iter(plan["captures"])
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: Response(next(captures)),
    )
    inventory = build_api_inventory(plan, "http://example.invalid")
    assert len(inventory["rows"]) == 4
    assert all(row["support_class"] == "strong" for row in inventory["rows"])
    assert "observer_site" not in str(inventory)
