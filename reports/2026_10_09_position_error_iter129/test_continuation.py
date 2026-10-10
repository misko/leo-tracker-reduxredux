from types import SimpleNamespace

from continuation import continue_slice
from ports import dependencies


def test_actual_continuation_admission_three_regions_both_arms_failures(tmp_path, monkeypatch):
    _, driver, adapter = dependencies()
    monkeypatch.setattr(driver, "case_identity", lambda case: {"same": "case"})
    plan, member = {}, dict(label="synthetic", binding={})
    digest = driver.canonical_digest(plan)
    discovery = tmp_path / "search"
    regions = [dict(east_km=float(i), north_km=0.0) for i in range(3)]
    driver.append(
        discovery / "result.json",
        dict(
            protocol_sha256=digest,
            label="synthetic",
            status="complete",
            searches={"native": dict(regions=regions)},
        ),
    )
    driver.append(discovery / "case.json", dict(protocol_sha256=digest, identity={"same": "case"}))
    for i in range(3):
        point = [float(i), 0.0]
        vector = [*point, *([0.0] * 7)]
        for key, value in (
            (["bootstrap", point], dict(satellite_indices=[0, 1], vector=vector)),
            (
                ["point", *point, "fitted-c"],
                dict(fit=dict(vector=vector, objective=1.0, converged=True)),
            ),
        ):
            driver.append(
                discovery / "points" / (driver.canonical_digest(key)[7:] + ".json"),
                dict(protocol_sha256=digest, key=key, status="complete", value=value),
            )
    calls = []

    class Expired(Exception):
        pass

    def claim(directory, phase, bound, *, maximum):
        assert phase == "baseline" and maximum == 2 and bound == digest
        return 1

    def recover(obs, bank, prior, trigger, stage):
        calls.append(trigger)

        def operation():
            if trigger["key"] == "point:1.0:0.0":
                raise ValueError("synthetic calibration rejection")
            return dict(calibration="synthetic")

        return dict(recovery=stage(trigger["key"], 90, operation), finals=[])

    def joint(obs, bank, prior, found, stage):
        assert len(found) == 3
        assert "rejection" in found["retained-1"]["recovery"]["reason"]
        return {"zero-c": {}, "fitted-c": {}}, {}, []

    namespace = {}
    exec("def load_case(document): return None", namespace)
    namespace.update(
        core=SimpleNamespace(HARD60_SCORE={}, RegionalSliceExpired=Expired),
        claim_slice=claim,
        recovered_region=recover,
        run_joint_stages=joint,
    )
    case = dict(
        observations=None,
        prior={},
        bank=SimpleNamespace(numbers=driver.np.array([1, 2])),
        identity={"input_manifest_sha256": "input"},
    )

    class Loader:
        load_case = namespace["load_case"]

        def __call__(self, binding):
            return case

    result = continue_slice(
        plan, member, "native", tmp_path / "native", discovery, Loader(), driver, adapter
    )
    assert result["status"] == "complete" and not result["fallback_available"]
    assert len(calls) == 3 and set(result["operational"]) == {"zero-c", "fitted-c"}
    assert all(t["identity"]["local_radius_km"] == 25.0 for t in calls)


def test_search_failure_preserved_without_loading_recording(tmp_path):
    _, driver, adapter = dependencies()
    plan, member = {}, dict(label="synthetic", binding={})
    discovery = tmp_path / "search"
    driver.append(
        discovery / "result.json",
        dict(protocol_sha256=driver.canonical_digest(plan), label="synthetic", status="failed"),
    )
    result = continue_slice(
        plan, member, "fixed", tmp_path / "fixed", discovery, None, driver, adapter
    )
    assert result["status"] == "not-run-search-failed" and result["operational"] == {}
    assert not result["fallback_available"]
