import pytest

from tools.pipeline_eval.qualification import hybrid_v5, hybrid_v5_results
from tools.pipeline_eval.qualification.v5_regional_blind import digest_json
from tools.pipeline_eval.qualification.v5_regional_reference import sha, write


def request(offer, tile):
    return dict(
        id=offer,
        session="capture",
        native="native.json",
        native_sha256="a" * 64,
        track_config="track.json",
        config_sha256="b" * 64,
        archive="tle",
        catalog_sha256="c" * 64,
        cutoff_utc_ns=1,
        tile=tile,
        screen_center=tile,
    )


def test_requires_paired_opaque_offers_for_same_capture(tmp_path):
    path = tmp_path / "requests.json"
    rows = [request("b", [40.1, 20]), request("a", [40, 20])]
    write(path, rows)
    assert hybrid_v5.read_rows(path) == rows[::-1]
    path.unlink()
    rows[0]["native_sha256"] = "d" * 64
    write(path, rows)
    with pytest.raises(ValueError, match="paired native capture"):
        hybrid_v5.read_rows(path)


def test_rejects_truth_and_unsealed_roster(tmp_path):
    manifest = tmp_path / "requests.json"
    lock = tmp_path / "detector-lock.json"
    write(manifest, [request("a", [40, 20]), dict(request("b", [40.1, 20]), truth=[40, 20])])
    write(lock, {"files": {"requests.json": sha(manifest)}})
    assert hybrid_v5.check_seal(lock, sha(lock), manifest) == sha(manifest)
    with pytest.raises(ValueError, match="truth-free"):
        hybrid_v5.read_rows(manifest)
    manifest.unlink()
    write(manifest, [request("a", [40, 20]), request("b", [40.1, 20])])
    with pytest.raises(ValueError, match="does not bind"):
        hybrid_v5.check_seal(lock, sha(lock), manifest)


def test_child_command_masks_controller_and_has_no_network(tmp_path):
    private, worker = tmp_path / "private", tmp_path / "worker"
    command = hybrid_v5.isolated(worker, 20, private)
    assert command[:3] == ["taskset", "-c", "20"]
    assert command[command.index("--tmpfs") + 1] == str(private)
    assert "--unshare-net" in command
    assert command[-2:] == [str(worker), "20"]


def test_only_shared_public_config_and_history_aliases_are_accepted(tmp_path):
    public = tmp_path / "public" / "hybrid"
    public.mkdir(parents=True)
    (public / "track.json").symlink_to(public.parent / "track-config.json")
    (public / "tle").symlink_to(public.parent / "tle")
    row = request("a", [40, 20])
    assert hybrid_v5.resolve_public(public, row) == {
        "native": "hybrid/native.json",
        "track_config": "track-config.json",
        "archive": "tle",
    }
    (public / "tle").unlink()
    (public / "tle").symlink_to(tmp_path / "private")
    with pytest.raises(ValueError, match="outside the arm/shared"):
        hybrid_v5.resolve_public(public, row)


def test_match_binds_offer_even_if_factor_and_catalogue_are_unchanged():
    actual = request("a", [40, 20])
    prediction = dict(
        id="case",
        method=hybrid_v5.METHOD,
        input_sha256=digest_json(actual),
        native_sha256=actual["native_sha256"],
        catalogue_sha256=actual["catalog_sha256"],
        result={
            "status": "ok",
            "boundary": "test native to synthetic position",
            "metrics": {},
            "arms": {arm: {"latlon": [40, 20]} for arm in ("c0", "fitted_c")},
        },
    )
    method = {hybrid_v5.METHOD: hybrid_v5.METHOD}
    assert set(hybrid_v5_results.normalized([prediction], {"case": actual}, method)) == {
        ("case", hybrid_v5.METHOD)
    }
    with pytest.raises(ValueError, match="offer bytes"):
        hybrid_v5_results.normalized([prediction], {"case": dict(actual, tile=[40, 21])}, method)


def test_donor_false_publication_has_no_geographic_error():
    requests = {
        "positive": request("a", [40, 20]),
        "omitted": request("b", [40, 21]),
        "donor": request("c", [40, 22]),
    }
    targets = {
        "positive": {"condition": "containing", "truth": [40, 20]},
        "omitted": {"condition": "omitted", "truth": [40, 20]},
        "donor": {"condition": "donor-only", "truth": None},
    }
    rows = {
        (ident, method): dict(
            input_sha256="same",
            native_sha256="native",
            catalogue_sha256="catalogue",
            result=dict(
                status="ok",
                metrics={},
                arms={arm: {"latlon": row["tile"]} for arm in ("c0", "fitted_c")},
            ),
        )
        for ident, row in requests.items()
        for method in hybrid_v5_results.MODES
    }
    _, scores = hybrid_v5_results.scored(
        rows, requests, targets, dict(positive="hybrid", omitted="hybrid", donor="donor-only")
    )
    assert len(scores) == 18
    assert all(
        r["false_publication"] and r["error_km"] is None for r in scores if r["id"] == "donor"
    )
