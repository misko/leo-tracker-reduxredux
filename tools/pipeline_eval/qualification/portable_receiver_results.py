"""Verify a relocated replay, package the exact build, and score both calibration arms."""

import argparse
import gzip
import io
import json
import subprocess
import tarfile
from hashlib import sha256
from pathlib import Path

from .. import figure_books, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km, validate_result
from . import adaptive_arrival_position as authority
from . import portable_receiver_demo as study
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from
from .winner_stream_results import scientific_result

PACKAGE = "portable-receiver.tar.gz"
RESULTS = "positions.jsonl.gz"
LOCK = "prediction-lock.json"
PROOF = "deployment-proof.json"
SCORES = "position-scores.csv"
METHOD = "portable_saved_iq"


def read_worker_file(path):
    """Read fresh owner-controlled artifacts with the incumbent archive reader account."""
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        return path.read_bytes()
    except PermissionError:
        return subprocess.check_output(["sudo", "-n", "-u", "leo", "cat", str(path)])


def archive(bundle, out, checksum):
    lock_path = whole_iq.checked(bundle / "files.json", checksum)
    files = whole_iq.read(lock_path)["files"]
    additions = ("README.md", "example-input.json", "requirements.txt")
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as output:
        for name in sorted([*files, *additions, "files.json"]):
            if name in additions:
                body = (out / ("USAGE.md" if name == "README.md" else name)).read_bytes()
            elif name == "files.json":
                body = lock_path.read_bytes()
            else:
                body = whole_iq.checked(bundle / name, files[name]).read_bytes()
            item = tarfile.TarInfo("portable-receiver/" + name)
            item.size = len(body)
            item.mode = 0o644
            output.addfile(item, io.BytesIO(body))
    write(out / PACKAGE, gzip.compress(stream.getvalue(), compresslevel=6, mtime=0))


def equal_science(new, old):
    return encoded(scientific_result(new)) == encoded(scientific_result(old))


def publish(bundle, scratch, python):
    report = study.REPORT
    plan = whole_iq.read(whole_iq.checked(report / study.PLAN, _sha(scratch / study.PLAN)))
    service = whole_iq.read(report / "service.json")
    whole_iq.checked(report / "service.log", service["log_sha256"])
    if service["exit_code"] or service["systemd"]["Result"] != "success":
        raise ValueError("a relocated receiver replay lacks a successful terminal service")
    root = scratch / "run"
    handoff = whole_iq.read(root / "request.json")
    if (
        handoff["request_sha256"] != plan["manifest_sha256"]
        or handoff["package_files_sha256"] != plan["package_sha256"]
        or handoff["detector_sha256"] != plan["detector_sha256"]
    ):
        raise ValueError("the relocated request differs from its sealed explicit inputs")
    raw = whole_iq.read(root / "raw-resources.json")
    solve = whole_iq.read(root / "position-resources.json")
    raw_lanes = [whole_iq.read(root / f"raw-{i}.json") for i in range(2)]
    for index, lane in enumerate(raw_lanes):
        if lane["authenticated_chunks"] == 0 or lane["cpus"] != [study.CPUS[index]]:
            raise ValueError("a raw lane did not verify its compressed payload and pin")
    marks = [raw["start"], raw["raw_end"], raw["handoff"], solve["start"], solve["end"]]
    for mark in marks:
        if (
            mark["memory.max"] != whole_iq.MEMORY
            or mark["memory.swap.max"] != 0
            or mark["memory.swap.current"] != 0
            or mark["memory.events"]["oom_kill"] != 0
            or mark["cgroup"] != marks[0]["cgroup"]
        ):
            raise ValueError("a stage left the physical capped service")
    if any(b["monotonic_s"] < a["monotonic_s"] for a, b in zip(marks, marks[1:], strict=False)):
        raise ValueError("recorded stage clocks went backward")
    prediction = whole_iq.read(root / "position.json")
    validate_result(prediction)
    parent = whole_iq.read(
        whole_iq.checked(authority.PARENT / LOCK, plan["stock_prediction_sha256"])
    )
    archive_positions = authority.parent_member(RESULTS, parent)
    old = next(
        row
        for row in rows_from(archive_positions)
        if row["id"] == study.CASE and row["method"] == authority.PARENT_METHOD["stock"]
    )
    old_factors = authority.parent_member(f"native/control/{study.CASE}.json.gz", parent)
    received_native = read_worker_file(root / "native.json")
    reference_native = gzip.decompress(old_factors.read_bytes())
    actual_sha = sha256(received_native).hexdigest()
    if (
        received_native != reference_native
        or actual_sha != old["native_sha256"]
        or actual_sha != handoff["native_sha256"]
        or not equal_science(prediction, old["result"])
    ):
        raise ValueError("relocated application differs from historical detector or solver outputs")
    fit_arms_files = whole_iq.read(bundle / "files.json")
    bundle_items = fit_arms_files["files"]
    python_assets = subprocess.check_output(
        [
            str(python),
            "-IB",
            "-c",
            "import importlib.metadata as m,json,sys; print(json.dumps("
            "dict(python=sys.version.split()[0], packages={x:m.version(x) for x in "
            "('numpy','scipy','sgp4','pydantic','zstandard','matplotlib','pyyaml')})))",
        ],
        text=True,
    )
    proof = dict(
        session=handoff["session"],
        native_sha256=actual_sha,
        all_native_bytes_identical=True,
        scientific_position_json_excluding_stage_times_identical=True,
        matched_archive_sha256=_sha(old_factors),
        request_sha256=handoff["request_sha256"],
        raw=raw,
        localization=solve,
        raw_lanes=raw_lanes,
        stage_wall_s={
            name: marks[i + 1]["monotonic_s"] - marks[i]["monotonic_s"]
            for i, name in enumerate(("raw", "assembly", "binding", "localization"))
        },
        app_total_bytes=plan["installed_component_bytes"],
        app_file_count=plan["installed_files"],
        capture_reader_source_count=fit_arms_files["capture_sources"],
        application_components={
            base: sum(
                (bundle / name).stat().st_size for name in bundle_items if name.startswith(base)
            )
            for base in ("capture/", "position/", "stock-wide.so", "receive.py")
        },
        external_python=json.loads(python_assets),
        sandbox=dict(
            relocated=True,
            private_network=True,
            source_checkout_masked=True,
            opt_masked=True,
            fresh_python_deps_only=True,
        ),
        service_name=service["unit"],
    )
    save_json(report / PROOF, proof)
    old = dict(old, method="portable_archived_stock")
    new = dict(old, method=METHOD, result=prediction)
    pack(report / RESULTS, [old, new])
    files = [
        study.PLAN,
        study.MANIFEST,
        "PROTOCOL.md",
        "service.json",
        "service.log",
        PROOF,
        RESULTS,
    ]
    files.extend(p.name for p in sorted(report.glob("preflight-*")))
    save_json(
        report / LOCK, dict(cases=[study.CASE], files={name: _sha(report / name) for name in files})
    )
    score(report)
    archive(bundle, report, plan["package_sha256"])
    save_json(
        report / "package-lock.json",
        dict(
            release_manifest_sha256=plan["package_sha256"],
            files={
                name: _sha(report / name)
                for name in (PACKAGE, "example-input.json", "requirements.txt")
            },
            architecture="x86_64 Linux",
        ),
    )


def score(out):
    report = study.REPORT
    lock = whole_iq.read(report / LOCK)
    for name, sha in lock["files"].items():
        whole_iq.checked(report / name, sha)
    _, (ref,) = held_references(None, lock["cases"])
    records = []
    for row in rows_from(report / RESULTS):
        for arm in ARMS:
            position = row["result"]["arms"][arm]
            records.append(
                dict(
                    id=row["id"],
                    method=row["method"],
                    arm=arm,
                    lat=position["latlon"][0],
                    lon=position["latlon"][1],
                    error_km=distance_km(position["latlon"], ref["truth"]),
                    conditional_rms_hz=position["rf_rms_hz"],
                    **{name + "_km": ref["reference"][name][arm]["error_km"] for name in ROLES},
                )
            )
    out.mkdir(parents=True, exist_ok=True)
    csv_file(out / SCORES, records)
    if out != report:
        return
    evidence = [PROOF, SCORES, LOCK, "service.json"]
    save_json(
        out / "chart-lock.json",
        dict(cases=lock["cases"], files={name: _sha(out / name) for name in (RESULTS, *evidence)}),
    )
    save_json(
        out / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="portable-saved-iq-position",
                    method=METHOD,
                    scope="roof",
                    cases="sealed",
                    title="Relocated saved-IQ receiver parity",
                    caption=(
                        "One complete capture through relocated stock and compact phase-release. "
                        "Identical position and RF outputs in both arms. Original v5 options use "
                        "capture-era factors."
                    ),
                    seal="chart-lock.json",
                    provenance=evidence,
                    series=[
                        dict(
                            key=key,
                            file=RESULTS,
                            value=method,
                            label=label,
                            native_field="paired_capture_sha256",
                            match=[
                                "tile",
                                "native_sha256",
                                "catalog_sha256",
                                "original_request_sha256",
                            ],
                        )
                        for key, method, label in (
                            ("one", METHOD, "Relocated receiver"),
                            ("stock", "portable_archived_stock", "Archive stock"),
                        )
                    ],
                )
            ],
        ),
    )
    figure_books.generate(out / "charts", ARMS, panel="screening", evidence=out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    full = modes.add_parser("publish")
    for name in ("bundle", "scratch", "python"):
        full.add_argument(name, type=Path)
    modes.add_parser("score").add_argument("out", type=local_output)
    args = parser.parse_args()
    if args.mode == "publish":
        publish(args.bundle, args.scratch, args.python)
    else:
        score(args.out)
