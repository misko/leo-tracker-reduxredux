"""Bind two blind compact-study offers to the complete original v5 numerical worker."""

import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path

from . import v5_regional_reference as reference

REQUIRED = {
    "id",
    "session",
    "native",
    "native_sha256",
    "track_config",
    "config_sha256",
    "archive",
    "catalog_sha256",
    "cutoff_utc_ns",
    "tile",
    "screen_center",
}
SHARED = ("session", "native_sha256", "config_sha256", "catalog_sha256", "cutoff_utc_ns")


def digest_json(data):
    return hashlib.sha256(
        json.dumps(data, separators=(",", ":"), sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def public_path(root, filename):
    path = Path(filename)
    if path.is_absolute() or not (root / path).resolve().is_relative_to(root):
        raise ValueError("sealed request paths must remain in the public packet directory")
    return root / path


def select_pair(rows):
    if not rows or any(set(row) != REQUIRED for row in rows):
        raise ValueError("expected the sealed truth-free compact-study request fields")
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("duplicate opaque offer identity")
    first = min(row["session"] for row in rows)
    pair = sorted((row for row in rows if row["session"] == first), key=lambda row: row["id"])
    if len(pair) != 2 or any(pair[0][key] != pair[1][key] for key in SHARED):
        raise ValueError("one paired native capture and causal options required")
    if pair[0]["tile"] == pair[1]["tile"]:
        raise ValueError("paired offers must supply different centers")
    return pair


def causal_inputs(archive, output, cutoff, newest):
    latest = []
    snapshots = {}
    for path in sorted(archive.rglob("*.tle")):
        stamp, declared = path.stem.split("-", maxsplit=1)
        stamp = int(stamp)
        if stamp >= cutoff:
            continue
        if path.name in snapshots:
            raise ValueError("duplicate filename in the source TLE archive")
        sha = reference.checked(path, declared)
        snapshots[path.name] = sha
        latest.append((stamp, sha))
        target = output / path.relative_to(archive)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        reference.checked(target, sha)
    if len(snapshots) < 2 or max(latest)[1] != newest:
        raise ValueError("causal history lacks the sealed received catalogue")
    return snapshots


def bind_template(template, row, native, config, history, catalogue):
    identity = dict(
        run_id="v5-ref-" + row["id"],
        session_id=row["session"],
        input_sha256="sha256:" + row["native_sha256"],
    )
    job = dict(
        template["job"],
        identity=identity,
        scan_identities=[row["session"]],
        title=row["id"],
        search_center=row["tile"],
        screen_center=row["screen_center"],
        native_input=dict(path=str(native), sha256=identity["input_sha256"]),
        track_config=dict(path=str(config), sha256="sha256:" + row["config_sha256"]),
        tle_root=str(catalogue),
        evaluation_reference=None,
    )
    return dict(template, job=job, causal_snapshots=history)


def prepare(rows, public, root):
    template, template_case = reference.roof_request()
    if template["job"]["evaluation_reference"] is not None:
        raise ValueError("template must have its inference-only reference null")
    first = rows[0]
    native = public_path(public, first["native"])
    config = public_path(public, first["track_config"])
    native_sha = reference.checked(native, first["native_sha256"])
    config_sha = reference.checked(config, first["config_sha256"])
    capture = reference.read(native)
    if (
        capture["source"]["session_id"] != first["session"]
        or capture["clock_anchor"]["before"]["realtime_ns"] != first["cutoff_utc_ns"]
    ):
        raise ValueError("clock cutoff or supplied session differs from its native measurements")
    catalogue = root / "causal-tle"
    source = public_path(public, first["archive"])
    offer_history = causal_inputs(
        source, catalogue, first["cutoff_utc_ns"], first["catalog_sha256"]
    )
    history_sha = digest_json(offer_history)
    staged_native = root / "native.json"
    staged_config = root / "track-config.json"
    for source_file, destination, digest in (
        (native, staged_native, native_sha),
        (config, staged_config, config_sha),
    ):
        shutil.copyfile(source_file, destination)
        reference.checked(destination, digest)
    jobs = []
    for row in rows:
        if (
            reference.checked(public_path(public, row["native"]), native_sha) != native_sha
            or reference.checked(public_path(public, row["track_config"]), config_sha) != config_sha
            or public_path(public, row["archive"]) != source
        ):
            raise ValueError("the paired regional offers use different physical evidence")
        reference.scientific_domain(row["tile"], row["screen_center"])
        request = bind_template(
            template, row, staged_native, staged_config, offer_history, catalogue
        )
        metadata = dict(
            id=row["id"],
            capture_id=row["session"],
            tile=dict(center=row["tile"], width_km=25),
            screen_center=row["screen_center"],
            native_sha256=native_sha,
            config_sha256=config_sha,
            catalog_sha256=row["catalog_sha256"],
            catalogue_sha256=row["catalog_sha256"],
            cutoff_utc_ns=row["cutoff_utc_ns"],
            history_sha256=history_sha,
            input_sha256=digest_json(row),
            original_template_sha256=template_case["request"]["sha256"],
        )
        jobs.append((metadata, request))
    return jobs, offer_history


def run(public, manifest_sha, root):
    controller_root = public.parent
    if public.name != "public" or root.is_relative_to(controller_root):
        raise ValueError("worker scratch must sit outside the masked controller directory")
    if root.is_relative_to("/mnt/qnap01"):
        raise ValueError("QNAP is read-only")
    report = reference.REPORT
    parity_file = report / "roof-parity.json"
    if not reference.read(parity_file)["exact"]:
        parity_file = report / "roof-retry" / "parity.json"
    if not reference.read(parity_file)["exact"]:
        raise ValueError("one exactly matched roof numerical replay is required")
    manifest = public / "requests.json"
    request_sha = reference.checked(manifest, manifest_sha)
    rows = select_pair(reference.read(manifest))
    root.mkdir(parents=True, exist_ok=False)
    jobs, history = prepare(rows, public, root)
    plan = report / "blind-plan.json"
    history_file = report / "causal-snapshots.json"
    template = jobs[0][1]
    reference.write(history_file, history)
    lock = dict(
        authorizing_manifest_sha256=request_sha,
        cases=[job[0] for job in jobs],
        causal_snapshot_inventory_sha256=reference.sha(history_file),
        roof_parity_file=str(parity_file.relative_to(report)),
        roof_parity_sha256=reference.sha(parity_file),
        adapter_sha256=reference.sha(Path(reference.__file__)),
        controller_sha256=reference.sha(Path(__file__)),
        cpu=reference.CPU,
        deadline_s=reference.LIMIT,
        memory_bytes=reference.MEMORY,
        original_options=dict(
            role=template["role"],
            model=template["model"],
            policy=template["policy"],
            job_execution_policy=template["job"]["execution_policy"],
            evaluation_reference=None,
            arms=reference.v5_lean.ARMS,
            width_km=reference.v5_lean.ROOF_WIDTH_KM,
            runtime=template["job"]["runtime"],
            frozen_source_sha256=template["source"]["sha256"],
            frozen_runner_sha256=reference.v5_lean.RUNNER_SHA256,
            native_binary_sha256=template["native_manifest"]["binary_sha256"],
        ),
    )
    reference.write(plan, lock)
    records = []
    for row, request in jobs:
        check = reference.run_request(request, root / row["id"], blind_dir=controller_root)
        finish = check["resources"].get("finish", {})
        records.append(
            dict(
                row,
                worker_wall_s=check["wall_s"],
                worker_cpu_s=finish.get("cpu_s"),
                worker_cgroup_peak_bytes=finish.get("memory_peak_bytes"),
                **check,
            )
        )
        reference.write(root / f"{row['id']}.receipt.json", records[-1])
        print(row["id"], check["result"]["status"], round(check["wall_s"], 2), flush=True)
    reference.checked(manifest, request_sha)
    reference.checked(Path(reference.__file__), lock["adapter_sha256"])
    reference.checked(Path(__file__), lock["controller_sha256"])
    predictions = report / "predictions.jsonl.gz"
    payload = b"".join(
        (json.dumps(row, sort_keys=True, allow_nan=False) + "\n").encode() for row in records
    )
    with predictions.open("xb") as stream:
        stream.write(gzip.compress(payload, mtime=0))
    reference.write(
        report / "prediction-lock.json",
        dict(
            cases=[row["id"] for row in records],
            files={path.name: reference.sha(path) for path in (plan, history_file, predictions)},
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("public", type=Path)
    cli.add_argument("manifest_sha")
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    run(args.public.resolve(), args.manifest_sha, args.root.resolve())
