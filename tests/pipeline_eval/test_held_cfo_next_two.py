import pytest

from reports.ALGO08.v3.held_cfo_next_two import catalogue_names, select


def case(n):
    name = f"DS30-{n:04}"
    return dict(case=name, assigned_rank=n, case_id=name, window_count=20, raw_identity_sha256="raw",
                manifest_raw_authority_sha256="original", order=["successor", "installed"],
                recording_state="complete", recording="fast8-auto-20261120-165618-tag-1-lower")


def status(n, both, successor=None):
    installed = "true" if both else "false"
    picked = installed if successor is None else successor
    # The opaque payload would fail any attempt to decode a score.
    return b"\n".join(
        f'{{"case":"DS30-{n:04}","algorithm":"{build}","verified_pair":{value},"arms":???}}'.encode()
        for build, value in (("installed", installed), ("successor", picked))
    )


def test_selection_uses_smoke_order_status_and_prior_tests_only():
    plan = dict(cases=[case(n) for n in range(1, 8)], smoke=["DS30-0003", "DS30-0001"])
    export = b"\n".join(status(n, n in {1, 2, 3, 5}) for n in reversed(range(1, 8)))
    result = select(plan, export, previous={"DS30-0004"}, after="DS30-0002", rank=3)
    assert [(r["execution_rank"], r["case"]) for r in result] == [(6, "DS30-0006"), (7, "DS30-0007")]
    assert all(r["nominal_capture_start_utc"] == "2026-11-20T16:56:18+00:00" for r in result)
    assert all(not row["roles"]["successor"]["verified_pair"] for row in result)


def test_no_ambiguous_original_status_or_rank():
    plan = dict(cases=[case(n) for n in range(1, 4)], smoke=[])
    export = b"\n".join((status(1, True), status(2, False, "true"), status(3, False)))
    with pytest.raises(ValueError, match="same pair status"):
        select(plan, export, after="DS30-0001", rank=1)
    with pytest.raises(ValueError, match="execution rank"):
        select(plan, export, after="DS30-0002", rank=1)


def test_manifest_metadata_normalizes_exact_names_without_reading_bodies():
    sha = "1"*64
    name = "1794865279908688927-"+sha+".tle"
    for manifest in ({name: sha}, {name: {"sha256": sha}}, ["/offline/source/"+name],
                     [{"filename": name, "sha256": "sha256:"+sha}]):
        assert catalogue_names(manifest) == {name: sha}
    with pytest.raises(ValueError, match="conflicting"):
        catalogue_names({name: "2"*64})
    with pytest.raises(ValueError, match="conflicting"):
        catalogue_names([name, "/same/name/"+name])
