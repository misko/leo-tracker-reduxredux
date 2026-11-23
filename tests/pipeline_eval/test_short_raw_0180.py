from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
    return import_module("short_raw_0180")


@pytest.fixture
def orbit_archive(tmp_path):
    original = tmp_path/"original"
    directory = original/"archive/space-track"
    directory.mkdir(parents=True)
    names = {}
    for timestamp in range(50, 100):
        payload = f"element set {timestamp % 3}\n".encode()
        digest = sha256(payload).hexdigest()
        name = f"{timestamp}-{digest}.tle"
        (directory/name).write_bytes(payload)
        names[name] = digest
    return original, directory, names


def test_causal_stage_deduplicates_only_payload_bytes_and_retains_original_names(trial, tmp_path, orbit_archive):
    original, directory, names = orbit_archive
    stage = tmp_path/"stage"
    stats = trial.stage_orbits(stage, original, names, cutoff=100)
    staged = stage/"archive/space-track"
    assert sorted(path.name for path in staged.iterdir()) == sorted(names)
    by_digest = {}
    for name, digest in names.items():
        src, dst = directory/name, staged/name
        assert dst.read_bytes() == src.read_bytes()
        assert not dst.samefile(src)
        if digest in by_digest:
            assert dst.samefile(by_digest[digest])
        by_digest[digest] = dst
    assert stats == dict(snapshots=50, unique=3, copied_bytes=sum(p.stat().st_size for p in by_digest.values()),
                         logical_bytes=sum(p.stat().st_size for p in staged.iterdir()))


@pytest.mark.parametrize("bad", ["count", "cutoff", "escape", "tampered"])
def test_causal_stage_rejects_wrong_membership_or_unverified_bytes(trial, tmp_path, orbit_archive, bad):
    original, directory, names = orbit_archive
    cutoff = 100
    first = next(iter(names))
    if bad == "count":
        names.pop(first)
        message = "snapshot count"
    elif bad == "cutoff":
        cutoff = 50
        message = "causal orbit entry"
    elif bad == "escape":
        names[f"../{first}"] = names.pop(first)
        message = "causal orbit entry"
    else:
        (directory/first).write_bytes(b"altered payload")
        message = "Unreviewed bootstrap input"
    with pytest.raises(ValueError, match=message):
        trial.stage_orbits(tmp_path/"stage", original, names, cutoff)


def test_causal_stage_rejects_over_budget_before_reading_payload(trial, tmp_path, orbit_archive, monkeypatch):
    original, directory, names = orbit_archive
    with (directory/min(names)).open("wb") as stream:
        stream.truncate(100 * 1024**2 + 1)
    monkeypatch.setattr(trial, "checked", lambda *_: pytest.fail("oversized payload was read"))
    with pytest.raises(ValueError, match="one-recording allowance"):
        trial.stage_orbits(tmp_path/"stage", original, names, cutoff=100)


@pytest.fixture
def admission(trial, tmp_path, monkeypatch):
    def sealed(path, document):
        data = json.dumps(document).encode()
        path.write_bytes(data)
        return sha256(data).hexdigest()

    diag = import_module("short_raw_diagnostic")
    sky = import_module("triage_bounds")
    physical = import_module("full_short_physical")
    geo = import_module("dense_geographic_trial")
    bulk = tmp_path/"bulk"
    bulk.mkdir()
    req, binding, library = (bulk/name for name in ("request.json", "binding.json", "cache.so"))
    library.write_bytes(b"reviewed library")
    offer = dict(center=[37.9, -122.5], screen_center=[37.5, -122.], width_km=25.)
    job = dict(evaluation_reference=None, search_center=offer["center"], screen_center=offer["screen_center"],
               tle_root=str(bulk/"tle"))
    case = dict(id="DS30-0180", recording=dict(window_count=92, segments=[
        {"path": "capture/segment/manifest.json", "sha256": "a"*64}]), regions=[{"center": offer["center"]}])
    events = []
    preflight = dict(members=2, observed_members=2, observed_file_pages=20, cached_pages=0, unavailable={})
    warm = preflight | {"cached_pages": 20}
    state = SimpleNamespace(job=job, case=case, size=111_464_875, cache=[preflight, warm.copy(), warm.copy()], events=events)
    real_checked = trial.checked

    def checked(path, pin):
        if path.name == "ds30-station-offer.json":
            return json.dumps(offer).encode()
        return real_checked(path, pin)

    def stage(target, source, entries, cutoff):
        events.append("orbits")
        assert source == Path(job["tle_root"]) and entries == {"snapshot": "sealed"} and cutoff == 101
        return dict(snapshots=50)

    def cache_check(store, recording, manifests, pages, query):
        assert recording == bulk/"capture"
        assert manifests == ((bulk/"capture/segment/manifest.json", "sha256:"+"a"*64),)
        result = state.cache.pop(0)
        events.append(("resident", result["cached_pages"]))
        return result

    def timed(command, env, target):
        assert (target.parent/"admission.json").is_file()
        events.append(("measurement", target.name))
        return {"exit_code": 0}

    def run(command, *args, **kwargs):
        if command[0] == "findmnt":
            return "tmpfs\n"
        assert "findfont" in command[-1]
        return SimpleNamespace(returncode=0)

    def launch():
        request_digest = sealed(req, dict(job=job, causal_snapshots={"snapshot": "sealed"}))
        case["request"] = {"path": req.name, "sha256": request_digest}
        monkeypatch.setattr(trial, "BINDING_SHA", sealed(binding, dict(case=case, orbit_cutoff_ns=101)))
        trial.launch(tmp_path/"publication")

    monkeypatch.setattr(trial, "BULK", bulk)
    monkeypatch.setattr(trial, "BINDING", binding)
    monkeypatch.setattr(trial, "checked", checked)
    monkeypatch.setattr(trial, "stage_orbits", stage)
    monkeypatch.setattr(trial.subprocess, "check_output", run)
    monkeypatch.setattr(trial.subprocess, "run", run)
    monkeypatch.setattr(geo, "host", lambda: {"cpu": [2]})
    monkeypatch.setattr(physical, "environment", lambda _: {})
    monkeypatch.setattr(diag, "CACHE_LIB", library)
    monkeypatch.setattr(diag, "CACHE_SHA", sha256(library.read_bytes()).hexdigest())
    monkeypatch.setattr(diag.cache_residency, "load_query", lambda _: object())
    monkeypatch.setattr(diag.cache_residency, "bound_snapshot", cache_check)
    monkeypatch.setattr(diag.pairs, "verified_v3", lambda _: {"version": "named"})
    monkeypatch.setattr(diag, "measure", timed)
    monkeypatch.setattr(sky, "warm_recording", lambda _: events.append("warm"))
    monkeypatch.setattr(sky, "ShortWindowReader", lambda _: SimpleNamespace(manifest=SimpleNamespace(
        chunks=[SimpleNamespace(compressed_bytes=state.size)])))
    return state, launch


def test_raw_admission_conditions_once_and_checks_residency_at_each_launch(admission, tmp_path):
    state, launch = admission
    launch()
    assert state.events == [
        ("resident", 0), "orbits", "warm", ("resident", 20), ("measurement", "stock"),
        ("resident", 20), ("measurement", "candidate"),
    ]
    saved = json.loads((tmp_path/"publication/admission.json").read_bytes())
    assert saved["conditioning"]["used"] is True
    assert saved["conditioning"]["bytes"] == 111_464_875


def test_candidate_cannot_launch_after_residency_changes(admission):
    state, launch = admission
    state.cache[2]["cached_pages"] = 19
    with pytest.raises(ValueError, match="not fully resident"):
        launch()
    assert ("measurement", "stock") in state.events
    assert ("measurement", "candidate") not in state.events
    assert state.events.count("warm") == 1


@pytest.mark.parametrize("changed", ["offer", "visit_count", "payload", "members", "unavailable"])
def test_changed_enrollment_or_payload_fails_before_conditioning(admission, changed):
    state, launch = admission
    if changed == "offer":
        state.job["evaluation_reference"] = {"latitude_deg": 37.9, "longitude_deg": -122.5}
    elif changed == "visit_count":
        state.case["recording"]["window_count"] = 93
    elif changed == "payload":
        state.size += 1
    elif changed == "members":
        state.cache[0]["members"] = 3
    else:
        state.cache[0]["unavailable"] = {"permission": 1}
    with pytest.raises(ValueError, match="enrollment|recording budget"):
        launch()
    assert "orbits" not in state.events and "warm" not in state.events
    assert all(event[0] != "measurement" for event in state.events)
