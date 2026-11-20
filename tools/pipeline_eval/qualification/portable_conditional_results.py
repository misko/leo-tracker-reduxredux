"""Package and cross-check the conditional receiver's relocated saved-IQ evidence."""

import argparse
import gzip
import io
import json
import tarfile
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, distribution, validate_result
from ..variants import second_on_miss
from ..variants.iq_stream import _read_prefix
from . import portable_conditional_build as package
from . import portable_conditional_lower as lower
from . import portable_conditional_trial as trial
from . import second_on_miss_roster as projected
from . import second_on_miss_whole as direct
from . import staggered_benchmark
from .full_v5_check import _sha
from .one_lane_whole_results import control_source
from .portable_receiver_results import equal_science, read_worker_file
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT
TAR = "portable-receiver-conditional.tar.gz"
DOCS = {"README.md", "example-input.json", "requirements.txt"}
read = whole_iq.read


def checked_member(folder, receipt, name):
    return whole_iq.checked(folder / name, receipt["files"][name])


def old_package(path):
    with tarfile.open(path) as archive:
        manifest = json.load(archive.extractfile("portable-receiver/files.json"))["files"]
        sizes = {name: archive.getmember(f"portable-receiver/{name}").size for name in manifest}
    return manifest, sizes


def footprint(sizes, staged_archive):
    assets = {name: size for name, size in sizes.items() if name not in DOCS}
    native = {n: s for n, s in assets.items() if ".so" in Path(n).name}
    return dict(
        application_files=len(assets),
        python_files=sum(n.endswith(".py") for n in assets),
        shared_objects=len(native),
        shared_object_bytes=sum(native.values()),
        application_bytes=sum(assets.values()),
        compressed_bytes=staged_archive.stat().st_size,
        inventory=sorted(native),
    )


def bundle(folder):
    source = read(REPORT / "source-lock.json")
    manifest = whole_iq.checked(folder / "files.json", source["package_manifest_sha256"])
    pins = read(manifest)["files"]
    old_path = whole_iq.checked(package.BASE_TAR, package.BASE_SHA)
    former = read(package.STAGGERED / "result-lock.json")
    staggered = checked_member(package.STAGGERED, former, "portable-receiver-staggered.tar.gz")
    old, sizes = old_package(old_path)
    if {name for name in old if pins.get(name) != old[name]} != {
        "capture/native_bridge.py",
        "receive.py",
    } or pins.keys() - old.keys() - DOCS != {
        "capture/conditional_capture.py",
        "capture/conditional_policy.py",
    }:
        raise ValueError("package changed more than the declared two-file optional adapter")
    dest = REPORT / TAR
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as tar:
        for name in sorted([*pins, "files.json"]):
            path = whole_iq.checked(folder / name, pins[name]) if name in pins else manifest
            body = path.read_bytes()
            entry = tarfile.TarInfo(f"portable-receiver/{name}")
            entry.size, entry.mode = len(body), 0o644
            tar.addfile(entry, io.BytesIO(body))
    write(dest, gzip.compress(stream.getvalue(), compresslevel=6, mtime=0))
    save_json(
        REPORT / "footprint.json",
        dict(
            stock=footprint(sizes, old_path),
            staggered=footprint(old_package(staggered)[1], staggered),
            conditional=footprint({n: (folder / n).stat().st_size for n in pins}, dest),
            added_shared_objects=[],
        ),
    )
    write(REPORT / "release-files.json", manifest.read_bytes())
    write(REPORT / "SHA256SUMS", f"{_sha(dest)}  {TAR}\n".encode())
    save_json(
        REPORT / "package-lock.json",
        dict(
            architecture="x86_64 Linux",
            package_manifest_sha256=_sha(manifest),
            files={
                name: _sha(REPORT / name)
                for name in (TAR, "release-files.json", "SHA256SUMS", "footprint.json", "USAGE.md")
            },
        ),
    )


def comparison(ident):
    if ident == lower.CASE:
        parent, owner = staggered_benchmark.FRESH, projected.REPORT
        source = whole_iq.checked(parent / "source-lock.json", staggered_benchmark.FRESH_PIN)
        archive = read(parent / "raw-prediction-lock.json")
        control = checked_member(parent, archive, f"native/control/{ident}.json.gz")
        stock = json.loads(gzip.decompress(control.read_bytes()))
        stock_sha = sha256(gzip.decompress(control.read_bytes())).hexdigest()
        mode = projected.METHOD
    else:
        parent = owner = direct.REPORT
        source = checked_member(parent, read(parent / "prediction-lock.json"), "source-lock.json")
        control = read(source)["cases"][ident]["control"]
        stock, stock_sha = control_source(control), control["native_sha256"]
        mode = direct.METHOD
    receipt = owner / "prediction-lock.json"
    lock = read(receipt)
    positions = rows_from(checked_member(owner, lock, "positions.jsonl.gz"))
    (reference,) = [r for r in positions if (r["id"], r["method"]) == (ident, mode)]
    case = read(source)["cases"][ident]
    if reference["catalog_sha256"] != case["catalog_sha256"] or reference["tile"] != case["tile"]:
        raise ValueError("independent position reference used a different physical query")
    direct_blob = (
        gzip.decompress(checked_member(owner, lock, f"native/{ident}.json.gz").read_bytes())
        if owner == direct.REPORT
        else None
    )
    return stock, stock_sha, reference, direct_blob, _sha(receipt)


def physical_boundary(folder, segments):
    records = {}
    for lane in range(2):
        for line in read_worker_file(folder / f"lane-{lane}.jsonl").splitlines():
            row = json.loads(line)
            if row["kind"] != "visit":
                continue
            seq = records.setdefault(row["segment"], [])
            seq.append((row["sequence"], row["visit"], row["status"]))
    result, offset = [], 0
    for index, seg in enumerate(segments):
        rows = records.pop(index)
        if [(seq, visit) for seq, visit, _ in rows] != [
            (i, i + offset) for i in range(seg["windows"])
        ]:
            raise ValueError("the complete relocated public reader omitted a boundary visit")
        result.append(dict(segment=index, first=rows[0], last=rows[-1], windows=len(rows)))
        offset += len(rows)
    if records:
        raise ValueError("unbound raw segments were processed")
    return result


def parity(stock, actual, centers, measured):
    expected, ledger = second_on_miss.project(stock, centers)
    if actual != expected:
        raise ValueError("relocated physical packets differ from the full-stock projection")
    if ledger != [
        {k: row[k] for k in ("visit", "rf_center_hz", "primary_receiver", "partner_required")}
        for row in measured
    ]:
        raise ValueError("actual causal primary and partner dispatch differ on a valid visit")
    hits = sum(not row["partner_required"] for row in ledger)
    if not 0 < hits < len(ledger):
        raise ValueError("both actual primary hits and misses must be exercised")
    return len(ledger), hits


def verify_run(work, ident, manifest_sha):
    run = work / ident
    folder = run / "actual"
    receipt = read(run / "service.json")
    log = whole_iq.checked(run / "service.log", receipt["log_sha256"])
    if receipt["exit_code"] != 0:
        raise ValueError(f"{ident} did not complete through both position arms: {log}")
    request = read(folder / "request.json")
    native_blob = read_worker_file(folder / "native.json")
    native_sha = sha256(native_blob).hexdigest()
    if (
        request["request_sha256"] != _sha(REPORT / f"{ident}-input.json")
        or request["package_files_sha256"] != manifest_sha
        or request["native_sha256"] != native_sha
        or request["detector_sha256"] != package.STOCK
        or request["detector"] != "second-on-miss"
    ):
        raise ValueError("completed replay changed its sealed portable inputs")
    centers = {}
    for s in request["segments"]:
        payload = _read_prefix(Path(s["path"]), 65_537)
        if sha256(payload).hexdigest() != s["sha256"]:
            raise ValueError("authenticated capture tuning manifest changed after the replay")
        physical = json.loads(payload)
        pairs = {
            (row["channel"], row["edge"]): row["rf_center_hz"]
            for row in physical["configuration"]["targets"]
        }
        if centers and centers != pairs:
            raise ValueError("integer physical RF changed within the qualified recording")
        centers = pairs
    stock, stock_sha, numerical, direct_blob, control_seal = comparison(ident)
    measured = [
        json.loads(s) for s in (folder / "conditional-visits.jsonl").read_bytes().splitlines()
    ]
    valid, hits = parity(stock, json.loads(native_blob), centers, measured)
    if (direct_blob is not None and native_blob != direct_blob) or numerical[
        "native_sha256"
    ] != native_sha:
        raise ValueError("relocated native bytes differ from the independent validation study")
    result = read(folder / "position.json")
    validate_result(result)
    if set(result["arms"]) != set(ARMS) or not equal_science(result, numerical["result"]):
        raise ValueError("the relocated package changed a geographic or RF solver value")
    raw, worker, fit = (
        read(folder / name)
        for name in ("raw-resources.json", "raw-0.json", "position-resources.json")
    )
    start, end = raw["start"], fit["end"]
    for mark in (start, raw["raw_end"], raw["handoff"], fit["start"], end):
        if (
            mark["memory.max"] != whole_iq.MEMORY
            or mark["memory.swap.max"]
            or mark["memory.swap.current"]
            or mark["memory.events"]["oom_kill"]
            or mark["cgroup"] != start["cgroup"]
        ):
            raise ValueError("relocated service left its real 512 MiB no-swap boundary")
    if worker["cpus"] != request["cpus"][:1] or worker["authenticated_chunks"] < 1:
        raise ValueError("chronological worker left its one native CPU or compressed IQ port")
    timings = [m["detector_wall_ns"] / 1e6 for m in measured]
    if valid + raw["counts"]["invalid_capture"] != request["count"]:
        raise ValueError("physical capture exclusions changed")
    output = REPORT / "receipts" / ident
    write(output / "service.log", log.read_bytes())
    for name in (
        "request.json",
        "position.json",
        "raw-resources.json",
        "raw-0.json",
        "position-resources.json",
    ):
        write(output / name, read_worker_file(folder / name))
    save_json(output / "service.json", receipt)
    write(
        output / "visits.jsonl.gz",
        gzip.compress(read_worker_file(folder / "conditional-visits.jsonl"), mtime=0),
    )
    binding = physical_boundary(folder, request["segments"])
    return dict(
        id=ident,
        edge=request["edge"],
        cpu=worker["cpus"][0],
        raw_window_count=request["count"],
        valid=valid,
        invalid=raw["counts"]["invalid_capture"],
        primary_hits=hits,
        partner_calls=valid - hits,
        physical_receiver_calls=2 * valid - hits,
        skipped_fraction_vs_two_rx=hits / (2 * valid),
        raw_wall_s=worker["wall_s"],
        raw_cpu_s=worker["cpu_s"],
        position_wall_s=end["monotonic_s"] - fit["start"]["monotonic_s"],
        position_cpu_s=(end["cpu.stat"]["usage_usec"] - fit["start"]["cpu.stat"]["usage_usec"])
        / 1e6,
        full_service_wall_s=receipt["wall_s"],
        cpu_through_position_s=(end["cpu.stat"]["usage_usec"] - start["cpu.stat"]["usage_usec"])
        / 1e6,
        cgroup_peak_bytes=end["memory.peak"],
        position_process_peak_rss_kib=end["rss_peak_kib"],
        authenticated_chunks=worker["authenticated_chunks"],
        compressed_bytes=worker["compressed_bytes"],
        detector_wall_p50_ms=distribution(timings)["p50"],
        detector_wall_p95_ms=distribution(timings)["p95"],
        detector_within_20ms=sum(t <= 20 for t in timings),
    ), dict(
        id=ident,
        exact_stock_projection=True,
        exact_direct_native=direct_blob is not None,
        raw_native_sha256=native_sha,
        stock_native_sha256=stock_sha,
        independent_control_lock_sha256=control_seal,
        numerical_payload_exact=True,
        position_status=result["status"],
        source_request_sha256=request["request_sha256"],
        segment_bounds=binding,
    )


def stage_figure(rows):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    names = [f"{r['id']} · {r['edge']}" for r in rows]
    raw = [r["raw_wall_s"] for r in rows]
    fit = [r["position_wall_s"] for r in rows]
    other = [r["full_service_wall_s"] - r["raw_wall_s"] - r["position_wall_s"] for r in rows]
    fig, (wall, memory) = plt.subplots(1, 2, figsize=(10.8, 4.3), layout="constrained")
    wall.barh(names, raw, color="#1e5ba1", label="Authenticate, decode and detect")
    wall.barh(names, fit, left=raw, color="#007c69", label="Compact fit")
    wall.barh(
        names,
        other,
        left=[a + b for a, b in zip(raw, fit, strict=True)],
        color="#a4adbb",
        label="Startup and handoff",
    )
    wall.set(xlabel="Complete replay wall (s)", title="Saved I/Q through both position arms")
    wall.legend(loc="lower center", bbox_to_anchor=(0.5, -0.32), frameon=False, fontsize=8)
    rss = [r["position_process_peak_rss_kib"] / 1024 for r in rows]
    group = [r["cgroup_peak_bytes"] / 1024**2 for r in rows]
    memory.barh(names, group, color="#d3dce5", label="Full 512 MiB cgroup")
    memory.barh(names, rss, color="#596c8d", label="Position process peak RSS")
    memory.set(xlabel="Peak (MiB)", title="Measured memory, zero swap")
    memory.legend(loc="lower center", bbox_to_anchor=(0.5, -0.32), frameon=False, fontsize=8)
    for ax in (wall, memory):
        ax.invert_yaxis()
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_axisbelow(True)
        ax.grid(axis="x", alpha=0.22)
    for extension in ("png", "pdf"):
        fig.savefig(REPORT / f"resources.{extension}", dpi=160, bbox_inches="tight")
    plt.close(fig)
    files = ("resources.csv", "resources.png", "resources.pdf", "result-lock.json")
    save_json(REPORT / "stage-lock.json", dict(files={n: _sha(REPORT / n) for n in files}))
    save_json(
        REPORT / "stage-figure.json",
        dict(
            version=1,
            id="portable-conditional-resources",
            title="Relocated conditional receiver",
            boundary="Saved I/Q authentication and decode through the compact position arms",
            sample="Three complete recordings, both recorded pilot edges",
            note="One chronological acquisition CPU. Physical 512 MiB cgroup, zero swap.",
            image="resources.png",
            pdf="resources.pdf",
            csv="resources.csv",
            seal="stage-lock.json",
        ),
    )


def publish(work, lower_work):
    lock = read(REPORT / "source-lock.json")
    lower_lock = read(REPORT / "lower-source-lock.json")
    if lower_lock["package_manifest_sha256"] != lock["package_manifest_sha256"]:
        raise ValueError("lower replay must use the same relocated package")
    cases = [*trial.CASES, lower.CASE]
    data = [
        verify_run(
            work if ident in trial.CASES else lower_work, ident, lock["package_manifest_sha256"]
        )
        for ident in cases
    ]
    result, proof = zip(*data, strict=True)
    csv_file(REPORT / "resources.csv", list(result))
    save_json(REPORT / "parity.json", dict(zip(cases, proof, strict=True)))
    files = [
        "source-lock.json",
        "lower-source-lock.json",
        "resources.csv",
        "parity.json",
        "package-lock.json",
    ]
    files += [
        str(path.relative_to(REPORT))
        for path in sorted((REPORT / "receipts").rglob("*"))
        if path.is_file()
    ]
    save_json(
        REPORT / "result-lock.json",
        dict(cases=cases, files={name: _sha(REPORT / name) for name in files}),
    )
    stage_figure(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=local_output)
    parser.add_argument("--upper", type=local_output)
    parser.add_argument("--lower", type=local_output)
    args = parser.parse_args()
    bundle(args.bundle)
    if args.upper and args.lower:
        publish(args.upper, args.lower)
