from pathlib import Path
from shutil import copyfile

import pytest

from tools.pipeline_eval.qualification import portable_receiver as runtime
from tools.pipeline_eval.qualification import portable_receiver_build as build


def assets(tmp_path):
    root = tmp_path / "package"
    (root / "position").mkdir(parents=True)
    copyfile(build.ROOT / "tools/pipeline_eval/cavity_entry.py", root / "position/__main__.py")
    base = tmp_path / "data"
    base.mkdir()
    segments = []
    for i in range(2):
        leaf = base / f"segment-{i}"
        leaf.mkdir()
        manifest = leaf / "manifest.json"
        runtime.save(
            manifest,
            dict(
                schema_version=2,
                status="complete",
                sample_rate_hz=10_000_000,
                window_ms=20,
                receiver_ids=[0, 1],
                sample_format="ci16_le",
                sample_layout="sample_receiver_iq",
                window_count=32,
                session_id=leaf.name,
                radio={"serial": "test"},
                configuration={"targets": [{"edge": "lower"}]},
            ),
        )
        segments.append(dict(path=str(manifest.relative_to(base)), sha256=runtime.digest(manifest)))
    catalog = base / "tle"
    catalog.mkdir()
    tle = catalog / "a.tle"
    tle.write_text("fixture")
    cfg = base / "track-config.json"
    runtime.save(cfg, {})
    manifest = base / "input.json"
    runtime.save(
        manifest,
        dict(
            schema="leo-portable-receiver-input/v1",
            segments=segments,
            tle=dict(path="tle", snapshots={"a.tle": runtime.digest(tle)}),
            track_config=dict(path=cfg.name, sha256=runtime.digest(cfg)),
            offer=dict(center=[40.0, -105.0], width_km=25.0),
            screen_center=[40.0, -105.0],
        ),
    )
    return root, manifest


def test_explicit_relative_input_and_exact_causal_members(tmp_path, monkeypatch):
    root, manifest = assets(tmp_path)
    monkeypatch.setattr(runtime, "ROOT", root)
    monkeypatch.chdir(tmp_path)
    value = runtime.bindings(manifest)
    assert value["archive"] == str(manifest.parent / "tle")
    assert value["count"] == 64
    (manifest.parent / "tle/extra.tle").write_text("bad extra")
    with pytest.raises(ValueError, match="snapshot inventory"):
        runtime.bindings(manifest)


def test_capture_checks_the_original_manifest_digest(tmp_path, monkeypatch):
    root, manifest = assets(tmp_path)
    monkeypatch.setattr(runtime, "ROOT", root)
    asset = manifest.parent / "segment-0/manifest.json"
    asset.write_bytes(asset.read_bytes() + b" ")
    with pytest.raises(ValueError, match="digest differs"):
        runtime.bindings(manifest)


def test_portable_source_closure_has_raw_decoder_and_no_database():
    source = build.ROOT / "src"
    names = {name.relative_to(source).as_posix() for name in build.closure(source)}
    assert "leo/storage/short_window.py" in names
    assert "leo/analysis/starlink/native_short_window.py" in names
    assert not any(
        name.startswith(("leo/catalog/", "leo/api/", "leo/qualification/")) for name in names
    )
    compile(build.bridge(), str(Path("native_bridge.py")), "exec")
