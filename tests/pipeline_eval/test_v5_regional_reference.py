import hashlib

import pytest

from tools.pipeline_eval.qualification.v5_regional_blind import (
    bind_template,
    causal_inputs,
    public_path,
    select_pair,
)
from tools.pipeline_eval.qualification.v5_regional_reference import (
    offered_validator,
    scientific_domain,
    v5_lean,
)


def test_metadata_guard_verifies_every_other_field_and_restores_the_real_offer():
    actual = {"search_center": [-28.2, 74.5], "screen_center": [-28.4, 74.1], "other": "fixture"}
    seen = []

    def validate(job):
        seen.append(job)
        assert job["other"] == "fixture"
        assert job["screen_center"] == actual["screen_center"]

    assert offered_validator(validate)(actual) is actual
    assert seen == [dict(actual, search_center=list(v5_lean.ROOF_CENTER))]
    assert actual["search_center"] == [-28.2, 74.5]


@pytest.mark.parametrize(
    "tile,screen",
    [
        ([89.97, 30], [88, 31]),
        ([21, 179.98], [21, 179.9]),
        ([21, 131], [21, -140]),
        ([False, 11], [0, 11]),
    ],
)
def test_local_original_region_rejects_out_of_model_geography(tile, screen):
    with pytest.raises(ValueError):
        scientific_domain(tile, screen)


def test_opaque_pair_selection_fixes_capture_and_rejects_mismatched_evidence():
    def row(offer, session, longitude):
        return dict(
            id=offer,
            session=session,
            native="native.json",
            native_sha256="01",
            track_config="config.json",
            config_sha256="02",
            archive="tle",
            catalog_sha256="03",
            cutoff_utc_ns=102,
            tile=[5, longitude],
            screen_center=[5, longitude],
        )

    first, second, other = row("b", "a", 50), row("a", "a", 52), row("c", "b", 71)
    assert select_pair([other, first, second]) == [second, first]
    with pytest.raises(ValueError, match="paired native"):
        select_pair([first, dict(second, native_sha256="04")])
    with pytest.raises(ValueError, match="truth-free"):
        select_pair([first, dict(second, truth=[5, 11])])


def test_tle_binding_keeps_only_strictly_prior_snapshots(tmp_path):
    archive = tmp_path / "prior" / "archive" / "space-track"
    archive.mkdir(parents=True)
    expected = {}
    for date in (1, 3, 4, 6):
        data = str(date).encode()
        sha = hashlib.sha256(data).hexdigest()
        path = archive / f"{date}-{sha}.tle"
        path.write_bytes(data)
        if date < 4:
            expected[path.name] = sha
    result = causal_inputs(
        archive.parent.parent, tmp_path / "bounded", 4, hashlib.sha256(b"3").hexdigest()
    )
    assert result == expected
    assert {p.name for p in (tmp_path / "bounded").rglob("*.tle")} == expected.keys()


def test_relocation_reuses_original_options_and_binds_new_truth_free_inputs(tmp_path):
    template = {
        "role": "baseline",
        "policy": "original-policy",
        "native_manifest": {"binary_sha256": "native-backend"},
        "job": {
            "runtime": {"numpy": "pinned"},
            "execution_policy": "validation-all-work",
            "search_center": list(v5_lean.ROOF_CENTER),
            "screen_center": [37.5, -122.0],
            "evaluation_reference": None,
        },
    }
    public = dict(
        id="opaque-offer",
        session="opaque-session",
        native_sha256="a" * 64,
        config_sha256="b" * 64,
        tile=[-32.1, -53.2],
        screen_center=[-32.0, -53.0],
    )
    archive = {"1-orbit.tle": "c" * 64}
    result = bind_template(
        template, public, tmp_path / "native", tmp_path / "config", archive, tmp_path / "tle"
    )
    job = result["job"]
    assert {k: result[k] for k in template if k != "job"} == {
        k: template[k] for k in template if k != "job"
    }
    assert job["runtime"] is template["job"]["runtime"]
    assert job["search_center"] == public["tile"]
    assert job["screen_center"] == public["screen_center"]
    assert job["evaluation_reference"] is None
    assert result["causal_snapshots"] is archive
    assert job["scan_identities"] == [public["session"]]
    assert job["native_input"]["sha256"] == job["identity"]["input_sha256"]


def test_public_packet_paths_cannot_reference_the_custodian(tmp_path):
    root = tmp_path / "public"
    root.mkdir()
    (root / "pointer").symlink_to(tmp_path / "private")
    with pytest.raises(ValueError, match="public packet directory"):
        public_path(root, "pointer/labels.json")
