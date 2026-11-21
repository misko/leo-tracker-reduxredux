"""Reserve, replay and lock the eight-session DS30 Gauss panel."""

import argparse
import itertools
import json
import os
import platform
import re
import socket
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ..variants import v5_lean, v5_orbit_domain, v5_secant_fit
from . import blind_compact_run, blind_compact_score, compact_history_replay
from .blind_compact_roster import BULK, DS29, METHODS, SALT, locator, seal, select
from .compact_orbit_policy import selected_mode
from .full_v5_check import _load_case, _sha
from .reverse_glrt_reference import digest, read_bound
from .reverse_glrt_report import read

WORK = BULK / "leo-dev/ds30-20261120"
DATA = WORK / "dataset"
OUT = Path(__file__).resolve().parents[3] / "reports/2026_11_20_ds30_fast"
SNAPSHOT = WORK / "snapshot"
ARCHIVE = BULK / "leo"
SOURCE_TOOL = DS29.parent / "input-tooling/prepare_snapshot.py"


def geometry(member):
    if (
        member["recording_state"] != "complete"
        or member["sample_rate_hz"] != 10_000_000
        or not member["session_id"]
        or not member["tracking_inputs"]
        or not member["raw_recording"]["segments"]
        or member["raw_recording"]["integrity_errors"]
    ):
        return False
    for s in member["raw_recording"]["segments"]:
        raw = Path(s["path"]).read_bytes()
        if digest(raw) != s["sha256"].removeprefix("sha256:"):
            raise ValueError("raw segment commitment changed")
        data = json.loads(raw)
        if (
            data.get("receiver_ids") != [0, 1]
            or data.get("sample_rate_hz") != 10_000_000
            or data["configuration"].get("window_ms") != 20
        ):
            return False
    return True


def snapshot_tools():
    if _sha(SOURCE_TOOL) != read(DS29 / "inventory.json")["tool_sha256"].removeprefix("sha256:"):
        raise ValueError("previous snapshot adapter changed")
    sys.path.insert(0, str(SOURCE_TOOL.parent))
    import prepare_snapshot

    return prepare_snapshot


def save_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("changed frozen input: " + str(path))
    else:
        with path.open("xb") as f:
            f.write(data)


def raw_locator(entry):
    path = Path(entry["path"])
    if path.is_relative_to(BULK):
        return locator(path, entry["sha256"])
    if not path.is_relative_to("/srv/postgres-nvme/fast-scan-recordings"):
        raise ValueError("unexpected DS30 replay input location")
    return dict(path=str(path), sha256=entry["sha256"].removeprefix("sha256:"))


def reserve():
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_scan import FastScanStore

    tools = snapshot_tools()
    manifest_path = DATA / "manifest.json"
    sha = _sha(manifest_path)
    if DATA.joinpath("manifest.sha256").read_text().split()[0] != "sha256:" + sha:
        raise ValueError("DS30 membership has changed")
    members = {r["dataset_label"]: r for r in read(manifest_path)["members"]}
    candidates = [dict(id=k, session_id=v["session_id"]) for k, v in members.items() if geometry(v)]
    chosen = select(candidates, set(), count=8)
    seal(
        OUT / "selection.json",
        dict(
            protocol_sha256=_sha(OUT / "PROTOCOL.md"),
            manifest_sha256=sha,
            salt=SALT,
            eligible_recordings=len(candidates),
            eligible_sessions=len({r["session_id"] for r in candidates}),
            selected=chosen,
        ),
    )
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshots = archive.list_snapshots("space-track")
    store = FastScanStore(ARCHIVE)
    template = read(DS29 / "template-request.json")
    if template["evaluation_reference"] is not None:
        raise ValueError("reference in request template")
    config_sha = template["track_config"]["sha256"]
    config_file = DS29 / "inputs/config.json"
    if _sha(config_file) != config_sha.removeprefix("sha256:"):
        raise ValueError("changed track configuration")
    save_bytes(SNAPSHOT / "inputs/config.json", config_file.read_bytes())
    sample = _load_case("DS29-0082")
    request = read_bound(sample["request"])
    config = dict(
        source=request["source"],
        native_manifest=request["native_manifest"],
        policies={"baseline": request["policy"]},
        output=str(WORK / "bindings"),
        cohorts={
            "DS30": dict(
                template=template, members=[], config_sha256=config_sha, snapshot=str(SNAPSHOT)
            )
        },
    )
    sys.path.insert(0, str(v5_lean.RUNNER))
    from evaluate_accuracy_repair import worker_request

    cases = []
    orders = list(itertools.permutations(METHODS))
    inputs = SNAPSHOT / "inputs"
    for i, candidate in enumerate(chosen):
        label = candidate["id"]
        member = members[label]
        payload, doc, run, selection = tools.native_evidence(member, store)
        cutoff = doc["clock_anchor"]["before"]["realtime_ns"]
        if cutoff > member["captured_utc_ns"]:
            raise ValueError("causal cutoff is later than the acquisition start")
        bundle = inputs / label
        native = bundle / "native.json"
        save_bytes(native, payload)
        hashes = {}
        for ref in tools.causal(snapshots, cutoff):
            name = ref.path.name
            shared = inputs / "causal-tle" / name
            if not shared.exists():
                save_bytes(shared, archive.read(ref).encode("ascii"))
            if _sha(shared) != ref.sha256:
                raise ValueError("archived orbit digest mismatch")
            link = bundle / "tle/archive/space-track" / name
            link.parent.mkdir(parents=True, exist_ok=True)
            if not link.exists():
                os.link(shared, link)
            if not link.samefile(shared):
                raise ValueError("changed per-session orbit archive")
            hashes[name] = ref.sha256
        config["cohorts"]["DS30"]["members"].append(
            dict(
                dataset_label=label,
                recording_id=member["recording_id"],
                session_id=member["session_id"],
                availability="available",
                input_sha256=tools.sha(payload),
                causal_snapshots=hashes,
            )
        )
        job = worker_request(config, dict(dataset="DS30", case=label, repetition=0), "baseline")
        if job["job"]["evaluation_reference"] is not None:
            raise ValueError("reference leaked into inference")
        path = bundle / "request.json"
        seal(path, job)
        case = dict(
            **candidate,
            panel="DS30",
            run_id=run,
            regions=sample["regions"],
            native=locator(native, _sha(native)),
            request=locator(path, _sha(path)),
            recording=dict(
                window_count=member["window_count"],
                segments=[raw_locator(s) for s in member["raw_recording"]["segments"]],
            ),
        )
        cases.append(
            dict(
                case=case,
                cpu=i,
                order=orders[i % len(orders)],
                causal_cutoff_utc_ns=cutoff,
                orbit_snapshots=len(hashes),
                native_selection=selection["policy"],
            )
        )
    seal(
        OUT / "roster.json",
        dict(
            protocol_sha256=_sha(OUT / "PROTOCOL.md"),
            selection_sha256=_sha(OUT / "selection.json"),
            dataset_manifest_sha256=sha,
            cases=cases,
        ),
    )
    predecessor = OUT / "predecessor-build.json"
    old = read(predecessor)
    builds = dict(
        libraries=old["libraries"],
        assets=old["assets"],
        previous_build_sha256=_sha(predecessor),
        roster_sha256=_sha(OUT / "roster.json"),
        sources={
            Path(m.__file__).name: _sha(Path(m.__file__))
            for m in (
                blind_compact_run,
                v5_secant_fit,
                v5_lean,
                v5_orbit_domain,
                compact_history_replay,
            )
        },
    )
    seal(OUT / "build.json", builds)
    print("Reserved", [r["id"] for r in chosen], flush=True)


def repair_on_known_failure(public, directory, mode):
    original = v5_secant_fit.run(public, directory, mode)
    log = directory / "worker.log"
    frames = (
        re.findall(r'File "[^"]+", line \d+, in ([^\n]+)', log.read_text()) if log.exists() else []
    )
    repair = selected_mode(original.get("reason"), frames[-1] if frames else None)
    if repair == "orbit_support":
        result = v5_orbit_domain.run(public, directory.parent / repair)
    elif repair == "history_support":
        result = v5_lean.run_bound_worker(
            public,
            directory.parent / repair,
            Path(compact_history_replay.__file__),
            worker_args=(str(directory / "orbit_projector.so"),),
        )
    else:
        result = original
    result["metrics"].update(
        stock_status=original["status"],
        stock_reason=original.get("reason"),
        applied_orbit_policy=repair,
    )
    return result


def replay_session(row):
    os.sched_setaffinity(0, {row["cpu"]})
    builds = read(OUT / "build.json")
    for method, path in blind_compact_run.LIBS.items():
        if _sha(path) != builds["libraries"][method]:
            raise ValueError("changed receiver library")
    for edge, expected in builds["assets"].items():
        if _sha(blind_compact_run.TWO_WORK / "embedded" / (edge + ".f32")) != expected:
            raise ValueError("changed receiver pilot")
    for method in row["order"]:
        blind_compact_run.arm(
            row["case"],
            method,
            row["cpu"],
            builds,
            work=WORK,
            output=OUT,
            solve=repair_on_known_failure,
        )


def run():
    if socket.gethostname().split(".")[0] != "gauss":
        raise ValueError("Gauss required for timing")
    cases = read(OUT / "roster.json")["cases"]
    if not (OUT / "host.json").exists():
        seal(
            OUT / "host.json",
            dict(
                hostname=socket.gethostname(),
                platform=platform.platform(),
                cpu_assignments={r["case"]["id"]: r["cpu"] for r in cases},
                load_at_start=os.getloadavg(),
            ),
        )
    with ProcessPoolExecutor(max_workers=len(cases)) as pool:
        list(pool.map(replay_session, cases))
    blind_compact_score.inventory(OUT, WORK)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("reserve", "run", "lock"))
    action = parser.parse_args().action
    if action == "reserve":
        reserve()
    elif action == "run":
        run()
    else:
        blind_compact_score.inventory(OUT, WORK)
