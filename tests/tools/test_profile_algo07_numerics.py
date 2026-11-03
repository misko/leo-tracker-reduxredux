"""Private numerical replay must preserve inputs and reject escaped evidence."""

import argparse
import json

import profile_algo07_numerics as profile
import pytest

from leo.cli.algo07_profile import digest, verify


def test_inventory_excludes_outputs_and_rejects_input_links(tmp_path):
    (tmp_path / "input.json").write_text("{}")
    (tmp_path / "candidate").mkdir()
    (tmp_path / "candidate/result.json").write_text("{}")
    assert profile.inventory(tmp_path) == {"input.json": digest(tmp_path / "input.json")}
    (tmp_path / "escaped.json").symlink_to(tmp_path / "input.json")
    with pytest.raises(ValueError, match="symbolic link"):
        profile.inventory(tmp_path)


def test_snapshot_relocates_proof_and_freezes_exact_reference(tmp_path, monkeypatch):
    from leo.storage.fast_graph_position_v6 import FastGraphPositionStoreV6

    source = tmp_path / "public"
    source.mkdir()
    (source / "history-bank.json").write_text("{}")
    (source / "input.json").write_text(json.dumps(dict(path=str(source / "history-bank.json"))))
    receipt = dict(path="public-terminal", sha256="frozen")
    monkeypatch.setattr(FastGraphPositionStoreV6, "status",
                        lambda *_: dict(state="complete", run_id="run"))
    monkeypatch.setattr(FastGraphPositionStoreV6, "plot_evidence",
                        lambda *_: dict(workspace=str(source), terminal_receipt=receipt))
    monkeypatch.setattr(FastGraphPositionStoreV6, "terminal", lambda *_: ({}, receipt))
    before = profile.inventory(source)
    output = tmp_path / "snapshot"
    profile.snapshot(argparse.Namespace(bulk_root=tmp_path, job="job", output=output))
    assert profile.inventory(source) == before
    assert verify(output / "frozen.json")["verified"]
    assert json.loads((output / "input/input.json").read_text())["path"] == str(
        output / "input/history-bank.json")
    (output / "input/history-bank.json").write_text("changed")
    assert not verify(output / "frozen.json")["verified"]


def test_trial_cannot_write_frozen_input(tmp_path):
    with pytest.raises(ValueError, match="outside frozen input"):
        profile.launch(argparse.Namespace(snapshot=tmp_path, output=tmp_path / "input/trial"))


def test_receipt_tree_excludes_concurrent_trial_but_keeps_descendants(tmp_path):
    paths = []
    for pid, parent in [(10, 1), (11, 10), (20, 2), (21, 20)]:
        p = tmp_path / f'{pid}.json'
        p.write_text(json.dumps(dict(pid=pid, parent_pid=parent)))
        paths.append(p)
    owned, direct = profile.receipt_tree(paths, 1)
    assert {p.stem for p in owned} == {'10', '11'}
    assert direct == [10]
