import json
from pathlib import Path

import pytest
from export_inputs import load_authority, main


def frozen_files(tmp_path: Path, dataset: str = "DS10") -> tuple[Path, list[str]]:
    selected = [f"scan-{index:02d}" for index in range(16)]
    captures = [
        {
            "session_id": session_id,
            "capture_start_utc_ns": 1_000_000_000 * index,
            "capture_end_utc_ns": 1_000_000_000 * (index + 1),
            "manifest_sha256": f"sha256:{index:064x}",
            "analysis_evidence_sha256": f"sha256:{index + 1:064x}",
            "sample_rate_hz": 2_500_000,
            "radio_id": "radio-test",
        }
        for index, session_id in enumerate(selected)
    ]
    manifest_path = tmp_path / f"{dataset.lower()}-manifest.json"
    manifest_bytes = json.dumps(
        {"dataset_id": dataset, "captures": captures}, separators=(",", ":")
    ).encode()
    manifest_path.write_bytes(manifest_bytes)
    units = [
        {"unit_id": f"single-{index}", "session_ids": [session_id], "size": 1}
        for index, session_id in enumerate(selected)
    ]
    units.extend(
        {
            "unit_id": f"pair-{index // 2}",
            "session_ids": selected[index : index + 2],
            "size": 2,
        }
        for index in range(0, 16, 2)
    )
    units.extend(
        {
            "unit_id": f"quad-{index // 4}",
            "session_ids": selected[index : index + 4],
            "size": 4,
        }
        for index in range(0, 16, 4)
    )
    selection_path = tmp_path / "selection.json"
    import hashlib

    selection_path.write_text(
        json.dumps(
            {
                "datasets": {
                    dataset: {
                        "manifest_path": str(manifest_path.resolve()),
                        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                        "selected": selected,
                        "units": units,
                    }
                }
            }
        )
    )
    return selection_path, selected


def test_load_authority_binds_dataset_manifest_and_nested_units(tmp_path):
    selection_path, selected = frozen_files(tmp_path)
    authority = load_authority("DS10", selected[5], selection_path=selection_path)
    assert authority["dataset"] == "DS10"
    assert authority["capture_entry"]["session_id"] == selected[5]
    assert authority["unit_ids"] == ["single-5", "pair-2", "quad-1"]
    assert authority["manifest_path"].is_absolute()


def test_load_authority_rejects_wrong_dataset_identity(tmp_path):
    selection_path, selected = frozen_files(tmp_path, dataset="DS10")
    selection = json.loads(selection_path.read_text())
    selection["datasets"]["DS11"] = selection["datasets"].pop("DS10")
    selection_path.write_text(json.dumps(selection))
    with pytest.raises(ValueError, match="identity is not DS11"):
        load_authority("DS11", selected[0], selection_path=selection_path)


def test_load_authority_rejects_manifest_digest_change(tmp_path):
    selection_path, selected = frozen_files(tmp_path)
    selection = json.loads(selection_path.read_text())
    manifest_path = Path(selection["datasets"]["DS10"]["manifest_path"])
    manifest_path.write_bytes(manifest_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="digest differs"):
        load_authority("DS10", selected[0], selection_path=selection_path)


def test_load_authority_rejects_non_nested_pair(tmp_path):
    selection_path, selected = frozen_files(tmp_path)
    selection = json.loads(selection_path.read_text())
    pairs = [unit for unit in selection["datasets"]["DS10"]["units"] if unit["size"] == 2]
    pairs[0]["session_ids"] = [selected[0], selected[2]]
    pairs[1]["session_ids"] = [selected[1], selected[3]]
    selection_path.write_text(json.dumps(selection))
    with pytest.raises(ValueError, match="nested consecutively"):
        load_authority("DS10", selected[0], selection_path=selection_path)


def test_cli_passes_explicit_dataset_and_output_root(monkeypatch, tmp_path, capsys):
    calls = []

    def fake_export(session_id, **kwargs):
        calls.append((session_id, kwargs))
        return {"dataset": kwargs["dataset"], "session_id": session_id}

    monkeypatch.setattr("export_inputs.export_input", fake_export)
    output_root = tmp_path / "outputs"
    main(["scan-00", "--dataset", "DS11", "--output-root", str(output_root)])
    assert calls[0][0] == "scan-00"
    assert calls[0][1]["dataset"] == "DS11"
    assert calls[0][1]["output_root"] == output_root
    assert json.loads(capsys.readouterr().out)["dataset"] == "DS11"
