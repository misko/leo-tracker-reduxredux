import json
import sys

import pytest
import stage_fast_shared_release as core


def manifest(tmp_path):
    source = tmp_path / "source.py"
    source.write_text('print("test")\n')
    return dict(
        schema=core.SCHEMA,
        model_id="a-shared-q-test",
        python=sys.executable,
        python_sha256=core.binding(sys.executable)["sha256"],
        entrypoint="bin/run.py",
        files=[
            dict(
                source=str(source),
                target="bin/run.py",
                sha256=core.binding(source)["sha256"],
                mode=0o444,
            )
        ],
    )


def test_explicit_staging_immutable_inventory_and_no_service_calls(tmp_path, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("No service/process execution while staging")

    monkeypatch.setattr(core.subprocess, "run", forbidden)
    doc = manifest(tmp_path)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(doc))
    stage = tmp_path / "release"
    result = core.stage(path, stage)
    assert result["state"] == "staged-not-activated" and result["service_changes"] == 0
    assert core.verify(stage) == result
    with pytest.raises(ValueError):
        core.stage(path, stage)
    stage.chmod(0o755)
    (stage / "extra").write_text("mutation")
    with pytest.raises(ValueError, match="inventory"):
        core.verify(stage)


@pytest.mark.parametrize("target", ["../escape", "/absolute", "bin/../escape", "stage.json"])
def test_target_traversal_rejected(tmp_path, target):
    doc = manifest(tmp_path)
    doc["files"][0]["target"] = target
    with pytest.raises(ValueError):
        core.validate(doc, tmp_path / "release")


def test_changed_source_rejected_before_destination_created(tmp_path):
    doc = manifest(tmp_path)
    (tmp_path / "source.py").write_text("changed")
    with pytest.raises(ValueError, match="Pinned source"):
        core.validate(doc, tmp_path / "release")
    assert not (tmp_path / "release").exists()


def test_narrow_deployed_patch_preserves_unrelated_bytes(tmp_path):
    source = tmp_path / "deployed.py"
    source.write_text("unrelated = 1\nold = 2\n")
    spec = dict(
        source=str(source),
        source_sha256=core.binding(source)["sha256"],
        replacements=[dict(old="old = 2", new="new = 3")],
        result_sha256=core.digest(b"unrelated = 1\nnew = 3\n"),
    )
    result = core.prepare_patch(spec, tmp_path / "prepared.py")
    assert source.read_text() == "unrelated = 1\nold = 2\n"
    assert result["patched"]["sha256"] == spec["result_sha256"]
    spec["replacements"][0]["old"] = "absent"
    with pytest.raises(ValueError, match="absent or ambiguous"):
        core.prepare_patch(spec, tmp_path / "bad.py")
