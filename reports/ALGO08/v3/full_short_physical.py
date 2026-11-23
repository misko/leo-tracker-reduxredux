"""Gate the single DS30-0016 raw full-short research transfer."""

import argparse
from hashlib import sha256
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter

from aperture_trial import BENCH, PAYLOAD, RELEASE, archive_identity, machine, read, write


HERE = Path(__file__).resolve().parent
GUARD_SHA = "d8a81c561bf8652d1e8521bcbf4b357198a483f5cb364613772e2e3ec1f77aad"
FAR_NATIVE = "sha256:858305692707e775a156da8d374eac41d488a976ffa9be939f1475e3c6f642ff"
FAR_ARCHIVE = "sha256:7aa06cab0502bcac70645a41a219bb6d53f1077f329e6f7ed79eb59a8794feec"
FAR_CENTER = [-32.95111322641392, 22.164484297751255]
PAIR = BENCH / "integration-shared/pairs/DS30-0016/pair.json"
PAIR_SHA = "e1f41ae18cb36cf6a5ab1aeaa0549816005ccec468b2c6e9b0c54d91de1b65c8"
REQUEST = Path("/srv/bulk/leo-dev/ds30-full-20261121/snapshot/inputs/DS30-0016/request.json")
REQUEST_SHA = "c167f3c3d833cfe21fdb0baf2d05ab30cd8e4673ec8ef4b4f6fbda9f56474110"
REGION_SHA = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
CACHE_LIB = BENCH / "ds30-cache-residency.so"
CACHE_SHA = "4f10e0a2e23121e184ee7d37767f55c29fefc158f4182a2dd99c4268ff2ce6ab"
ORDER = ("stock", "candidate")
ISSUED, ADMITTED = 808, 713


def checked(path, digest):
    if sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError(f"Pinned input changed: {path}")
    return path


def authorize_gate(path):
    row = read(path)
    identity = row["result"]["identity"]
    if (not row["passed"] or row["guard_sha256"] != GUARD_SHA
            or identity["case"] != "south-far" or identity["mode"] != "all-primary"
            or identity["native_sha256"] != FAR_NATIVE or identity["archive"]["snapshots_sha256"] != FAR_ARCHIVE
            or identity["offer"] != dict(center=FAR_CENTER, screen_center=FAR_CENTER, width_km=25.0)
            or any(sha256((HERE / k).read_bytes()).hexdigest() != v for k, v in row["source_sha256"].items())
            or not verify_gate(row["result"], row["proof"], row["catalogue"])):
        raise ValueError("The frozen bilateral far proof did not authorize the physical pair")
    return row


def verify_gate(result, audit, catalogue):
    if len(audit) != 1:
        return False
    proof = audit[0]["result"]
    receivers = proof.get("receivers", {})
    return (result["status"] == "withheld" and result["reason"] == "both_receivers_support_far_exterior"
            and not result["attempts"] and not result["ranks"] and not result.get("science")
            and proof.get("complete") is True and proof.get("would_withhold") is True
            and set(map(str, receivers)) == {"1", "2"}
            and all(row.get("unique_exterior") is True for row in receivers.values())
            and catalogue.get("catalogue_handoff") == 1)


def gate(output):
    from full_family_amortized_trial import run

    guard = PAYLOAD / "tools/pipeline_eval/variants/experimental/regional_bound_guard.py"
    if sha256(guard.read_bytes()).hexdigest() != GUARD_SHA:
        raise ValueError("The installed exterior proof changed")
    audit, counts, prepared = [], {}, {}

    def load(case):
        from leo.contracts.digests import canonical_digest
        from mixed_aperture_crossed import prepare

        native, archive, offer, identity, paid = prepare(case, "all-primary")
        if (not paid or identity["native_sha256"] != canonical_digest(native)
                or identity["offer"] != offer or identity["archive"] != archive_identity(archive)):
            raise ValueError("The southern gate does not bind the original packet, offer and archive")
        prepared.update(archive=archive, identity=identity)
        return native, archive, offer, identity, paid

    def scope():
        from early_region import preflight
        from leo.operations.tle_archive import TleArchiveReader

        return preflight(TleArchiveReader(prepared["archive"]), audit, counts)

    with TemporaryDirectory() as tmp:
        report = Path(tmp) / "gate.json"
        run("south-far", "control", report, load_saved_inputs=load, evidence_context=scope)
        result = read(report)
    passed = (result["identity"] == prepared["identity"]
              and archive_identity(prepared["archive"]) == prepared["identity"]["archive"]
              and verify_gate(result, audit, counts))
    pins = {name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
        "early_region.py", "prepared_exterior.py", "mixed_aperture_crossed.py", "full-short-physical-protocol.md")}
    write(output, dict(passed=passed, source_sha256=pins, guard_sha256=GUARD_SHA,
                       proof=audit, catalogue=counts, result=result))


def assigned(short_binary):
    from leo.contracts.digests import canonical_digest
    from full_short_raw import SHORT_SHA

    pair = read(checked(PAIR, PAIR_SHA))
    source = read(checked(REQUEST, REQUEST_SHA))
    stock = pair["runs"]["baseline"]
    region_file = checked(Path(pair["region"]), REGION_SHA)
    root = Path(source["job"]["tle_root"])
    archive = archive_identity(root)
    if (canonical_digest(source["causal_snapshots"]) != archive["snapshots_sha256"]
            or read(region_file) != stock["receipt"]["region"]
            or stock["receipt"]["window_count"] != ISSUED or stock["receipt"]["counts"]["processed"] != ADMITTED):
        raise ValueError("Original DS30-0016 offer, causal archive or visit count changed")
    return dict(recording=pair["recording"], raw_authority=stock["raw_authority"], archive=archive,
                region_file=str(region_file), offered_region=read(region_file),
                short_binary=str(checked(short_binary.resolve(strict=True), SHORT_SHA)),
                prior_pair_sha256=PAIR_SHA, archive_request_sha256=REQUEST_SHA, offer_sha256=REGION_SHA,
                session=stock["receipt"]["session_id"])


def environment(output):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (HERE, PAYLOAD, RELEASE / "src", RELEASE, HERE.parents[2]))),
               MPLCONFIGDIR=str(output / "fonts"))
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE", "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    return env


def run(output, gate_path, short_binary):
    from leo.storage.fast_scan import FastScanStore
    from tools.pipeline_eval.qualification.cache_residency import bound_snapshot, load_query
    from tools.pipeline_eval.qualification.paired_publication import child_usage

    authorize_gate(gate_path)
    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(v != "1" for v in host["threads"].values())):
        raise ValueError("Single low-priority Gauss slot required")
    request = assigned(short_binary)
    output.mkdir(exist_ok=False)
    bind = output / "request.json"
    recording = Path(request["recording"])
    store = FastScanStore(output)
    session, inventory_sha, inventory = store.inventory(recording, verify_windows=False)
    if session != request["session"] or inventory["window_count"] != ISSUED:
        raise ValueError("Original sealed inventory differs")
    manifests = tuple((Path(row["path"]) / "manifest.json", row["manifest_digest"]) for row in inventory["segments"])
    request.update(inventory_sha256=inventory_sha, gate_sha256=sha256(gate_path.read_bytes()).hexdigest(),
                   inventory_pins=[dict(path=str(path), sha256=pin) for path, pin in manifests])
    write(bind, request)
    query = load_query(checked(CACHE_LIB, CACHE_SHA))
    page_size = os.sysconf("SC_PAGE_SIZE")
    env = environment(output)
    python = str(RELEASE / "venv/bin/python")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=20)
    for arm in ORDER:
        cached_before = bound_snapshot(store, recording, manifests, page_size, query)
        write(output / f"{arm}-cache-before.json", cached_before)
        if cached_before["members"] != cached_before["observed_members"]:
            raise ValueError("Could not observe every signed compressed member")
        started, before = perf_counter(), child_usage()
        job = subprocess.run([python, "-BPs", str(Path(__file__).resolve()), "worker", arm, str(output / arm),
                              str(bind), str(gate_path)], env=env, capture_output=True, text=True, timeout=75)
        clocks = dict(elapsed_s=perf_counter()-started,
                      **{key: value-before[key] for key, value in child_usage().items()})
        write(output / f"{arm}-process.json", dict(clocks=clocks, machine=host, exit_code=job.returncode))
        if job.returncode:
            raise RuntimeError(f"{arm} exited {job.returncode}: {job.stderr[-4000:]}")
        write(output / f"{arm}-cache-after.json", bound_snapshot(store, recording, manifests, page_size, query))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    subs.add_parser("gate").add_argument("output", type=Path)
    pair = subs.add_parser("run")
    for name in ("output", "gate_path", "short_binary"):
        pair.add_argument(name, type=Path)
    child = subs.add_parser("worker")
    child.add_argument("arm", choices=ORDER)
    for name in ("output", "request_path", "gate"):
        child.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    action = args.pop("action")
    if action == "worker":
        from full_short_raw import worker

        worker(**args)
    else:
        (gate if action == "gate" else run)(**args)
