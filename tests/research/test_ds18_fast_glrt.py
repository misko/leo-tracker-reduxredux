import json

from tools.compare_ds18_fast_glrt import digest, select_panel, summarize


def test_selection_is_frozen_before_outcomes_and_accounts_for_other_members(tmp_path):
    captures = []
    for i, (rate, kind) in enumerate(
        ((2500000, "published"), (10000000, "published"), (2500000, "firmware_archive"))
    ):
        metadata = {
            "receipt": {
                "events": [{"visit_index": j, "target": {"channel": j % 4 + 1}} for j in range(40)]
            }
        }
        payload = json.dumps(metadata).encode()
        name = f"meta-{i}.json"
        (tmp_path / name).write_bytes(payload)
        captures.append(
            {
                "dataset_label": f"DS18-{i:03d}",
                "session_id": f"scan-{i}",
                "sample_rate_hz": rate,
                "source_kind": kind,
                "metadata_snapshot": name,
                "metadata_snapshot_sha256": digest(payload),
                "recording_manifest_sha256": digest(payload),
            }
        )
    manifest = json.dumps({"captures": captures}).encode()
    (tmp_path / "manifest.json").write_bytes(manifest)
    (tmp_path / "seal.json").write_text(json.dumps({"files": {"manifest.json": digest(manifest)}}))
    panel = select_panel(tmp_path, tmp_path / "out", per_channel=2)
    assert panel == select_panel(tmp_path, tmp_path / "out", per_channel=2)
    assert [m["status"] for m in panel["members"]] == [
        "selected",
        "unsupported_rate",
        "unpublished_archive",
    ]
    assert len(panel["members"][0]["visit_indices"]) == 8


def test_pair_gate_retains_strong_other_receiver_and_compares_fractional_margin():
    results = []
    for edge in ("lower", "upper"):
        probes = [
            {"receiver_id": rx, "candidates": [{"fractional_margin": value}]}
            for rx, value in ((0, 0.2), (1, 0.03))
        ]
        results.append(
            {
                "dataset_label": "DS18-test",
                "session_id": "test",
                "visit_index": len(results),
                "target": {"edge": edge, "channel": 1},
                "fast_scores": [{"margin": 0.001}, {"margin": 0.02}],
                "baseline_probes": probes,
                "recomputed": probes,
                "fast_ms": 0.5,
                "glrt_ms": 100,
            }
        )
    rows, summary = summarize(results)
    assert summary["max_abs_margin_delta"] == 0
    assert summary["strong_retained"] == summary["existing_strong_rx_windows"] == 2
    assert all(r["pair_pass"] for r in rows)
