from importlib import import_module
from hashlib import sha256
import json
from pathlib import Path

import pytest

from leo.contracts.digests import canonical_digest


def test_full_catalogue_route_is_explicit_for_raw_and_saved_publication(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    module = import_module("joint_publication")
    calls = []
    monkeypatch.setattr(module, "run", calls.append)
    args = [piece for key in ("recording", "archive", "region", "output") for piece in ("--" + key, str(tmp_path / key))]
    module.main(args)
    assert not calls[-1].full_catalogue
    for source in ([], ["--saved", str(tmp_path / "detections.json"), "--saved-digest", "ref"]):
        module.main([*args, *source, "--full-catalogue", "--verify-images"])
        assert calls[-1].full_catalogue and calls[-1].verify_images
    with pytest.raises(SystemExit):
        module.main([*args, "--stock-control", "--full-catalogue"])


@pytest.mark.parametrize("wrong", [None, "digest", "session", "inventory", "receiver"])
def test_replay_requires_all_saved_input_bindings(wrong, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    verified_saved = import_module("joint_publication").verified_saved
    native = dict(source=dict(session_id="session", input_manifest_sha256="inventory"),
                  provenance=dict(detector_sha256="sha256:receiver"))
    args = dict(expected=canonical_digest(native), session="session", inventory_digest="inventory", receiver="receiver")
    if wrong:
        args[{"digest": "expected", "inventory": "inventory_digest"}.get(wrong, wrong)] = "wrong"
        with pytest.raises(ValueError):
            verified_saved(native, **args)
    else:
        assert verified_saved(native, **args) is native


def test_recorded_raw_pair_binds_decoded_positions_and_saved_science():
    root = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    source = (root / "measurements/joint-south-raw-pair.json").read_bytes()
    runs = json.loads(source)["runs"]
    audit = json.loads((root / "development/joint-south-audit.json").read_bytes())
    assert audit["raw_pair_sha256"] == sha256(source).hexdigest()
    assert runs["candidate"]["native_file_sha256"] == runs["baseline"]["native_file_sha256"]
    assert audit["scientific"]["candidate"] == audit["scientific"]["saved"]
    for name, row in runs.items():
        assert row["receipt"]["window_count"] == 1200 and row["receipt"]["decision"] == "complete"
        images = row["evidence"]["images"]
        assert len(images) == 8
        pixel_file = (root / f"development/joint-{name}-position.png").read_bytes()
        assert "sha256:" + sha256(pixel_file).hexdigest() == images["position"]["sha256"]


def test_publication_mode_is_optional_and_routes_are_exclusive(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    publication = import_module("joint_publication")
    called = []
    monkeypatch.setattr(publication, "run", called.append)
    options = [item for name in ("recording", "archive", "region", "output")
               for item in ("--" + name, str(tmp_path / name))]
    publication.main(options)
    assert not called[-1].stock_control and not called[-1].signed_finish
    publication.main([*options, "--stock-control"])
    assert called[-1].stock_control and not called[-1].signed_finish
    publication.main([*options, "--signed-finish"])
    assert called[-1].signed_finish and not called[-1].stock_control
    with pytest.raises(SystemExit):
        publication.main([*options, "--stock-control", "--signed-finish"])


@pytest.mark.parametrize("field", ["raw_authority", "arms", "owners", "reason", "artifacts",
                                  "scientific_digests", "terminal", "decoded", None])
def test_signed_transfer_validates_every_stock_evidence_binding(field, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    transfer = import_module("signed_0374_transfer")
    original = dict(raw_authority="raw", arms={}, owners={}, reason=None, artifacts=[],
                    scientific_digests={}, receipt={"terminal_sha256": "original"})
    selected = dict(original)
    images = {"position": {"rgba_sha256": "original", "size": [1680, 960]}}
    decoded = dict(images=images, grid="fresh grid including timing")
    expected = dict(images=images, grid="archived grid including timing")
    if field == "decoded":
        decoded = {"images": {"position": {"rgba_sha256": "other"}}}
    elif field == "terminal":
        selected["receipt"] = dict(terminal_sha256="other")
    elif field is not None:
        selected[field] = "changed"
    if field is None:
        assert all(transfer.verify_stock(selected, original, decoded, expected).values())
    else:
        with pytest.raises(ValueError, match="Saved stock comparison changed"):
            transfer.verify_stock(selected, original, decoded, expected)


def test_owner_comparison_distinguishes_identity_and_predictive_role(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    transfer = import_module("signed_0374_transfer")
    original = dict(selected_rows={"c0": [["same", 1, "conditional"], ["role", 2, "conditional"],
                                         ["owner", 3, "predictive"], ["removed", 1, "conditional"]]})
    candidate = dict(selected_rows={"c0": [["same", 1, "conditional"], ["role", 2, "predictive"],
                                          ["owner", 4, "predictive"], ["new", 1, "conditional"]]})
    assert transfer.owner_changes(original, candidate)["c0"] == dict(
        stock=4, candidate=4, shared=3, removed=1, new=1, changed_norad=1, changed_role=1,
    )


def test_recorded_signed_transfer_binds_both_saved_publication_pngs():
    root = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    evidence = json.loads((root / "measurements/signed-DS30-0374-publication.json").read_bytes())
    stock, signed = (evidence["runs"][name] for name in ("stock", "signed"))
    assert all(stock["archived_stock_checks"].values())
    assert stock["source_sha256"] == signed["source_sha256"]
    assert stock["raw_authority"] == signed["raw_authority"]
    assert signed["route_details"]["decision"] == "complete"
    assert signed["route_details"]["signed"]["status"] == "unqualified"
    for record, mode in ((stock, "stock"), (signed, "candidate")):
        assert record["solve"]["grid_complete"]
        assert record["solve"]["objective_replay"] == {"c0": 0, "fitted_c": 0}
        assert len(record["evidence"]["images"]) == 8
        png = (root / f"development/signed-0374-{mode}-position.png").read_bytes()
        assert record["evidence"]["images"]["position"]["sha256"] == "sha256:" + sha256(png).hexdigest()
