from pathlib import Path

import pytest

from reports.ALGO08.v3 import strict_cairo_0016 as trial


def test_command_reuses_raw_cli_settings_and_changes_only_storage_and_destination(tmp_path):
    prior = ["timeout", "--kill-after=2s", "75s", "python", "-IB", "/old/exact_named_raw.py",
             "--recording", "/original", "--archive", "/causal", "--region", "/offer", "--output", "/old/out",
             "--history-risk-route", "--cairo-six-sheets"]
    packed = {"map": "/stage/map", "map_sha256": "sha256:123", "codec": "/stage/codec"}

    command = trial.quote(prior, tmp_path, packed)

    assert command[:5] == prior[:5]
    assert command[5] == str(trial.HERE/"exact_named_raw.py")
    assert command[6:13] == prior[6:13]
    assert command[13:16] == [str(tmp_path), "--history-risk-route", "--cairo-six-sheets"]
    assert command[16:] == ["--strict-packed-eight", "--packed-ci16-map", packed["map"],
                            "--packed-ci16-map-sha256", packed["map_sha256"], "--packed-ci16-codec", packed["codec"]]
    assert prior[13] == "/old/out"
    with pytest.raises(ValueError, match="qualified original-input"):
        trial.quote(command, tmp_path, packed)
    with pytest.raises(ValueError, match="qualified original-input"):
        trial.quote(prior[:-1], tmp_path, packed)


def test_conversion_source_uses_only_private_stage_paths(tmp_path):
    signed = {"files": [{"kind": "manifest", "relative": "segment0/manifest.json", "signed_sha256": "sha256:a"},
                        {"kind": "payload", "relative": "segment0/iq.zst", "signed_sha256": "sha256:b"}]}

    source = trial.source_inputs(signed, tmp_path)

    assert Path(source["recording"]) == tmp_path/trial.original.RECORDING.name
    assert source["manifests"] == [{"path": source["recording"] + "/segment0/manifest.json", "digest": "sha256:a"}]
    assert source["issued"] == 808
    assert source["compressed_bytes"] == 991_734_597


def test_candidate_specific_setup_charged_on_ready_and_first_use():
    budget = trial.price(7, .5, 5, 12, 8)

    assert budget["ready_elapsed_s"] == 7.5
    assert budget["charged_first_s"] == 12.5
    assert budget["ready_ratio_to_stock"] == pytest.approx(1.6)
    assert budget["charged_first_ratio_to_stock"] == pytest.approx(.96)
    assert budget["ready_saving_vs_cairo_s"] == .5
