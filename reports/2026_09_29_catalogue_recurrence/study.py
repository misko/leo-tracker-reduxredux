"""Resolve exact archived rosters and census the complete frozen corpus."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
AUTH = HERE.parent / "2026_09_28_full_manifest_inputs/checkpoints/09-full-ready"
PRIOR = HERE.parent / "2026_09_29_candidate_transfer_support"
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"


def read(p):
    return json.loads(p.read_text())


def save(p, data):
    with p.open("x") as f:
        json.dump(data, f, indent=2, allow_nan=False)


def digest(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(bindings):
    for n, h in bindings.items():
        assert digest(ROOT / n) == h, n


def prepare():
    command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        str(HERE),
        "-p",
        "test_core.py",
        "-v",
    ]
    with (HERE / "tests.log").open("x") as f:
        r = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    save(HERE / "test-receipt.json", dict(command=command, exit_code=r.returncode))
    assert r.returncode == 0
    authority = read(AUTH / "panel-inputs.json")
    old = read(AUTH / "evidence-sha256.json")
    bindings = {}
    assert all(
        g["ready"] and g["requested_records"] == g["validated_records"] for g in authority["groups"]
    )
    assert [(g["dataset_id"], g["requested_records"]) for g in authority["groups"]] == [
        ("DS7", 88),
        ("DS8", 65),
        ("DS9", 105),
    ]
    for g in authority["groups"]:
        assert [item["session_id"] for item in g["inputs"]] == g["session_ids"]
        manifest = read(ROOT / g["manifest_path"])
        captures = sorted(
            manifest["captures"], key=lambda r: (r["capture_start_utc_ns"], r["session_id"])
        )
        assert [c["session_id"] for c in captures] == g["session_ids"]
        bindings[g["manifest_path"]] = digest(ROOT / g["manifest_path"])
        assert bindings[g["manifest_path"]] == old[g["manifest_path"]]
        for item in g["inputs"]:
            for a in item["artifacts"]:
                p = Path(a["path"])
                n = str(p.relative_to(ROOT))
                h = digest(p)
                assert "sha256:" + h == a["sha256"]
                bindings[n] = h
    for p in (
        AUTH / "panel-inputs.json",
        PRIOR / "result.json",
        PRIOR / "evidence-sha256.json",
        ROOT / "tools/ds7_export_baseline.py",
    ):
        n = str(p.relative_to(ROOT))
        bindings[n] = digest(p)
    prev = read(PRIOR / "evidence-sha256.json")["sha256"]
    assert (
        bindings[str((PRIOR / "result.json").relative_to(ROOT))]
        == prev[str((PRIOR / "result.json").relative_to(ROOT))]
    )
    save(
        HERE / "plan.json",
        dict(groups=authority["groups"], archive_root="/var/lib/leo/tle", expected_scans=258),
    )
    for p in HERE.iterdir():
        if p.is_file():
            bindings[str(p.relative_to(ROOT))] = digest(p)
    save(HERE / "input-seal.json", dict(sha256=bindings))
    print("Frozen 258 scans with verified input bytes", flush=True)


def child():
    import gzip
    import inspect
    from collections import defaultdict

    import numpy as np
    from core import map_rows, support_counts
    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris

    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records, parse_element_sets

    plan = read(HERE / "plan.json")
    needed = {}
    entries = []
    for g in plan["groups"]:
        for ordinal, item in enumerate(g["inputs"]):
            paths = item["artifacts"]
            obs = read(Path(next(a["path"] for a in paths if a["kind"] == "observations")))
            m = read(
                Path(
                    next(
                        a["path"]
                        for a in paths
                        if a["kind"] == "candidates" and a["path"].endswith(".json")
                    )
                )
            )
            assert m["session_id"] == obs["session_id"] == item["session_id"]
            assert m["tracks_sha256"] == next(
                a["sha256"] for a in paths if a["kind"] == "observations"
            )
            key = m["baseline_snapshot_sha256"]
            assert key not in needed or needed[key] == m["catalogue_size"]
            needed[key] = m["catalogue_size"]
            entries.append((g["dataset_id"], ordinal, item, obs, m))
    archive = TleArchiveReader(Path(plan["archive_root"]))
    refs = archive.list_snapshots()
    rosters = {}
    directory = HERE / "snapshots"
    directory.mkdir(exist_ok=False)
    for key, size in sorted(needed.items()):
        matching = [r for r in refs if r.digest == key]
        assert matching, key
        ref = min(matching, key=lambda r: (r.collected_utc_ns, r.provider))
        payload = archive.read(ref)
        raw = payload.encode()
        assert hashlib.sha256(raw).hexdigest() == key.removeprefix("sha256:")
        filtered, excluded = exclude_labelled_starlink_debris(payload)
        catalogue = parse_element_sets(filtered)
        records = parse_element_set_records(filtered)
        numbers = list(catalogue.satellite_numbers)
        assert numbers == [r.satellite_number for r in records]
        map_rows(numbers, [], size)
        filename = key.removeprefix("sha256:") + ".txt.gz"
        (directory / filename).write_bytes(gzip.compress(raw, mtime=0))
        rosters[key] = dict(
            numbers=numbers,
            size=size,
            excluded=len(excluded),
            provider=ref.provider,
            collected_utc_ns=ref.collected_utc_ns,
            raw_snapshot="snapshots/" + filename,
            filtered_sha256=hashlib.sha256(filtered.encode()).hexdigest(),
        )
    save(HERE / "rosters.json", rosters)
    runtime = []
    sources = HERE / "runtime_sources"
    sources.mkdir(exist_ok=False)
    for function in (exclude_labelled_starlink_debris, TleArchiveReader, parse_element_sets):
        p = Path(inspect.getfile(function))
        target = sources / p.name
        target.write_bytes(p.read_bytes())
        runtime.append(
            dict(
                module=function.__module__,
                path=str(p),
                sha256=digest(p),
                copy=str(target.relative_to(HERE)),
            )
        )
    save(HERE / "runtime.json", dict(python=sys.version, sources=runtime))
    scans = []
    donors = defaultdict(set)
    for ds, ordinal, item, obs, m in entries:
        tracks = []
        observed = {t["track_id"]: t for t in obs["tracks"]}
        bankpath = Path(next(a["path"] for a in item["artifacts"] if a["path"].endswith(".npz")))
        with np.load(bankpath, allow_pickle=False) as bank:
            for t in m["tracks"]:
                ids = bank[f"candidate_ids_{t['index']}"].tolist()
                assert len(ids) == t["candidate_count"]
                numbers = map_rows(
                    rosters[m["baseline_snapshot_sha256"]]["numbers"], ids, m["catalogue_size"]
                )
                source = observed[t["track_id"]]
                tracks.append(
                    dict(
                        track_id=t["track_id"],
                        ids=ids,
                        numbers=numbers,
                        receiver_id=source["receiver_id"],
                        rf_hz=source["rf_hz"],
                    )
                )
                for n in numbers:
                    donors[n].add(item["session_id"])
        scans.append(
            dict(
                dataset=ds,
                session_id=item["session_id"],
                start_utc_ns=obs["start_utc_ns"],
                block=f"{ds}_{ordinal // 8:02d}",
                snapshot=m["baseline_snapshot_sha256"],
                tracks=tracks,
            )
        )
    byscan = {s["session_id"]: s for s in scans}
    assert len(byscan) == 258
    rawrows = []
    for s in scans:
        for outside in (False, True):
            counts = support_counts(s, donors, byscan, outside)
            for t in s["tracks"]:
                rawrows.append(
                    dict(
                        dataset=s["dataset"],
                        session_id=s["session_id"],
                        track_id=t["track_id"],
                        outside_block=outside,
                        candidates=len(t["numbers"]),
                        supported_candidates=sum(counts[n] >= 2 for n in t["numbers"]),
                    )
                )
    panel_scans = read(PRIOR / "result.json")["scans"]
    strong = defaultdict(set)
    mapped = []
    for s in panel_scans:
        target = byscan[s["session_id"]]
        rows = []
        bytrack = {t["track_id"]: t for t in target["tracks"]}
        for t in s["tracks"]:
            assert t["ids"] == bytrack[t["track_id"]]["ids"]
            numbers = bytrack[t["track_id"]]["numbers"]
            rows.append(dict(**t, numbers=numbers))
            for n, w in zip(numbers, t["weights"], strict=True):
                if w * t["signal_responsibility"] >= 0.5:
                    strong[n].add(s["session_id"])
        mapped.append(dict(**{k: v for k, v in s.items() if k != "tracks"}, tracks=rows))
    panelindex = {s["session_id"]: dict(s, block=s["panel"]) for s in mapped}
    panelrows = []
    for s in panelindex.values():
        for outside in (False, True):
            counts = support_counts(s, strong, panelindex, outside)
            for t in s["tracks"]:
                panelrows.append(
                    dict(
                        dataset=s["panel"][:3],
                        session_id=s["session_id"],
                        track_id=t["track_id"],
                        outside_panel=outside,
                        strong_mass=sum(
                            w
                            for n, w in zip(t["numbers"], t["weights"], strict=True)
                            if counts.get(n, 0) >= 2
                        ),
                    )
                )
    save(
        HERE / "result.json",
        dict(
            scans=scans,
            raw_rows=rawrows,
            panel_scans=mapped,
            panel_rows=panelrows,
            physical_candidate_scan_multiplicity={str(n): len(v) for n, v in donors.items()},
        ),
    )
    print(
        "Mapped",
        len(rosters),
        "snapshots;",
        len(scans),
        "scans;",
        len(rawrows) // 2,
        "tracks",
        flush=True,
    )


def launch():
    bindings = read(HERE / "input-seal.json")["sha256"]
    verify(bindings)
    available = (
        int(
            next(
                line.split()[1]
                for line in Path("/proc/meminfo").read_text().splitlines()
                if line.startswith("MemAvailable:")
            )
        )
        * 1024
    )
    assert available >= 5 * 1024**3
    command = [
        "sudo",
        "-n",
        "/usr/bin/time",
        "-v",
        "-o",
        str(HERE / "resources.txt"),
        "timeout",
        "--kill-after=5s",
        "120s",
        "prlimit",
        "--as=4294967296",
        "nice",
        "-n",
        "19",
        "env",
        "OPENBLAS_NUM_THREADS=1",
        PYTHON,
        str(HERE / "study.py"),
        "child",
    ]
    save(HERE / "launch.json", dict(command=command, available_bytes=available))
    with (HERE / "terminal.log").open("x") as f:
        r = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
    save(HERE / "exit.json", dict(exit_code=r.returncode))
    verify(bindings)
    for p in HERE.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            bindings[str(p.relative_to(ROOT))] = digest(p)
    save(HERE / "seal.json", dict(sha256=bindings))
    assert r.returncode == 0
    print("Bounded mapping and census complete", flush=True)


if __name__ == "__main__":
    {"prepare": prepare, "launch": launch, "child": child}[sys.argv[1]]()
