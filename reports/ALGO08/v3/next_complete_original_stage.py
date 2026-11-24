"""Stage the sole selected signed input on /tmp during one strict idle opportunity."""

import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
from shutil import disk_usage
import stat
import subprocess
import sys
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]
BULK = Path("/srv/bulk")
SOURCE_ROOT = BULK/"leo/fast-scan-recordings"
BINDINGS = BULK/"leo-dev/ds30-full-20261121/bindings"
LOCK = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
CACHE = Path("/tmp/leo-algo08v2-2x-bench/ds30-cache-residency.so")
CACHE_PIN = "4f10e0a2e23121e184ee7d37767f55c29fefc158f4182a2dd99c4268ff2ce6ab"
OFFER = Path("/tmp/leo-algo08v2-2x-bench/integration02/ds30-station-offer.json")
OFFER_PIN = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
MIN_FREE = 4*1024**3
SECONDS = 1200
MB = 1024**2


def emit(path, value):
    with path.open("x") as file:
        json.dump(value, file, indent=2, sort_keys=True, allow_nan=False)
        file.write("\n")


def checked_local(path, digest, size=None):
    body = path.read_bytes()
    if (size is not None and len(body) != size) or sha256(body).hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError(f"Signed metadata differs: {path}")
    return body


def row(path, digest, kind, size=None):
    path = Path(path)
    info = path.lstat()
    if (not path.is_relative_to(BULK) or path.resolve(strict=True) != path or not stat.S_ISREG(info.st_mode)
            or size is not None and size != info.st_size or not info.st_size):
        raise ValueError(f"Source is not the exact signed physical extent: {path}")
    return dict(path=path, size=info.st_size, sha256=digest, kind=kind)


def scoped_rows(member):
    raw = member["raw_recording"]
    root = Path(raw["root"])
    if root.parent != SOURCE_ROOT or raw["integrity_errors"]:
        raise ValueError("Expected a single exact original root from the signed roster")
    manifests = [row(m["path"], m["sha256"], "manifest") for m in raw["segments"]]
    life = [row(m["path"], m["sha256"], "lifecycle") for m in member["recording_metadata"]]
    files = manifests+life
    for c in raw["chunks"]:
        files.append(row(c["index_path"], c["index_sha256"], "index", c["index_bytes"]))
        files.append(row(c["payload_path"], c["compressed_sha256"], "payload", c["compressed_bytes"]))
    if len({m["path"] for m in files}) != len(files) or any(not m["path"].is_relative_to(root) for m in files):
        raise ValueError("The input plan contains a duplicate or out-of-scope filename")
    return root, files


def cache_sample(files):
    from tools.pipeline_eval.qualification.cache_residency import cache_snapshot, load_query

    checked_local(CACHE, CACHE_PIN)
    query, page = load_query(CACHE), os.sysconf("SC_PAGE_SIZE")
    state = cache_snapshot([(item["path"].parent, item["path"].name, item["size"]) for item in files], page, query)
    if state["unavailable"] or state["members"] != state["observed_members"]:
        raise ValueError("The named exact source's complete residency must be observable")
    return state


def causal_rows(request, cutoff):
    from leo.contracts.digests import canonical_digest

    names = request["causal_snapshots"]
    job = request["job"]
    if (not names or job["evaluation_reference"] is not None
            or any(Path(name).name != name or int(name.split("-", 1)[0]) >= cutoff for name in names)):
        raise ValueError("Expected bounded original causal archive members")
    archive = Path(job["tle_root"])/"archive/space-track"
    files = [(name, row(archive/name, pin, "tle")) for name, pin in sorted(names.items())]
    return files, canonical_digest(names)


def run(root):
    from guarded_cfo_0016_stage import BLOCK, RATE, Pacing, copy_member
    from guarded_stage_idle import IdleAdmission, IdleWindowExpired
    from next_complete_original import DATASET, DATASET_SHA, checked, enrollment

    started, cpu = perf_counter(), process_time()
    usage = resource.getrusage(resource.RUSAGE_SELF)
    if (not root.is_absolute() or root.parent != Path("/tmp") or root.exists()
            or subprocess.check_output(["findmnt", "-n", "-o", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs"
            or os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15
            or subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip() != "idle"
            or (BLOCK, RATE) != (MB, 2*MB)):
        raise ValueError("Expected one private idle-I/O slot on CPU2 in /tmp")
    selected = enrollment()["selected"]
    if not selected:
        raise ValueError("No sized original can finish within the guarded envelope")
    member, = (m for m in checked(DATASET, DATASET_SHA)["members"] if m["dataset_label"] == selected["case"])
    original, files = scoped_rows(member)
    total = sum(item["size"] for item in files)
    official_device = original.stat().st_dev
    available = int(next(line for line in Path("/proc/meminfo").read_text().splitlines()
                         if line.startswith("MemAvailable:")).split()[1])*1024
    if (available-total < MIN_FREE or disk_usage(root.parent).free-total < MIN_FREE
            or total >= SECONDS*RATE):
        raise ValueError("The selected complete original exceeds memory or time headroom")
    before = cache_sample(files)
    local_roots = [Path(location)/original.name for location in ("/tmp", "/dev/shm", "/srv/postgres-nvme/fast-scan-recordings")]
    local = {str(path): dict(present=path.exists(), redirects=path.is_symlink(),
                             same_original=path.exists() and path.resolve(strict=True) == original) for path in local_roots}
    if any(value["present"] and not value["same_original"] for value in local.values()):
        raise ValueError("An independent local copy needs exact authentication before reading new original bytes")
    root.mkdir(mode=0o700)
    emit(root/"preflight.json", dict(selected=selected, before=before, local=local, memory_available_bytes=available,
         waveform_authority=member["raw_authority_digest"], complete_source_bytes=total,
         original_members=[dict(item, path=str(item["path"])) for item in files]))

    device = Path(f"/sys/dev/block/{os.major(official_device)}:{os.minor(official_device)}/stat")
    deadline = started+SECONDS
    pacing = Pacing(root, total, 0, idle=True, device=device, deadline=deadline)
    idle = IdleAdmission(device, deadline, pacing.record)
    counts, completed, material = Counter(), [], {}
    reason = None
    stage = root/original.name
    binding = BINDINGS/(selected["case"]+".json")
    controller = root/"control"
    controller.mkdir()

    def copy(item, target, lock):
        target.parent.mkdir(parents=True, exist_ok=True)
        offset = pacing.copied
        try:
            copy_member(item["path"], target, item["size"], item["sha256"], lock, pacing,
                        journal=root/"checkpoint.json", admission=idle, required_device=official_device)
        finally:
            counts[item["kind"]] += pacing.copied - offset
        completed.append(dict(relative=str(target.relative_to(root)), length=item["size"], sha256=item["sha256"]))

    try:
        with LOCK.open("rb") as lock:
            copy(row(binding, selected["binding_sha256"], "binding"), controller/"binding.json", lock)
            bound = json.loads((controller/"binding.json").read_bytes())
            case, cutoff = bound["case"], bound["orbit_cutoff_ns"]
            if (case["id"] != selected["case"] or case["recording"]["window_count"] != selected["visits"]
                    or case["valid_visits"] != selected["admitted"]
                    or [(str(BULK/m["path"]), m["sha256"].removeprefix("sha256:")) for m in case["recording"]["segments"]]
                    != [(str(m["path"]), m["sha256"].removeprefix("sha256:")) for m in files if m["kind"] == "manifest"]):
                raise ValueError("The pinned native enrollment differs from the frozen selection")
            for name in ("request", "native"):
                entry = case[name]
                copy(row(BULK/entry["path"], entry["sha256"], name), controller/(name+".json"), lock)
            request = json.loads((controller/"request.json").read_bytes())
            snapshots, archive_pin = causal_rows(request, cutoff)
            offer = json.loads(checked_local(OFFER, OFFER_PIN))
            job = request["job"]
            if offer["center"] != job["search_center"] or offer["screen_center"] != job["screen_center"]:
                raise ValueError("The original signed job has a different operator offer")
            (controller/"offer.json").write_bytes(checked_local(OFFER, OFFER_PIN))
            material = dict(case=selected["case"], session=case["session_id"], cutoff_utc_ns=cutoff,
                            native_sha256=case["native"]["sha256"], request_sha256=case["request"]["sha256"],
                            archive_sha256=archive_pin, snapshots=len(snapshots), offer_sha256=OFFER_PIN)
            emit(root/"causal-admission.json", material)
            direct = before["cached_pages"] == before["observed_file_pages"]
            archive_bytes = sum({item["sha256"]: item["size"] for _, item in snapshots}.values())
            pacing.total = pacing.copied + archive_bytes + (0 if direct else total)
            if (pacing.total-pacing.copied > RATE*(deadline-perf_counter()-1)
                    or available-pacing.total < MIN_FREE or disk_usage(root.parent).free-(pacing.total-pacing.copied) < MIN_FREE):
                raise ValueError("The signed original plus causal archive cannot fit the remaining bounded envelope")

            if direct:
                reason = "original_direct_resident"
            else:
                for item in files:
                    copy(item, stage/item["path"].relative_to(original), lock)
            # Keep the actual original archive names. A repeated signed body can
            # be materialized by a local hardlink once its checksum has passed.
            by_digest = {}
            for name, item in snapshots:
                target = root/"tle/archive/space-track"/name
                prior = by_digest.get(item["sha256"])
                if prior is None:
                    copy(item, target, lock)
                    by_digest[item["sha256"]] = target
                else:
                    target.hardlink_to(prior)
    except (IdleWindowExpired, RuntimeError, OSError, ValueError, KeyError) as exc:
        reason = f"{type(exc).__name__}: {exc}"
    finally:
        after = cache_sample(files)
        now = resource.getrusage(resource.RUSAGE_SELF)
        verified_recording = [item for item in completed if item["relative"].startswith(original.name+"/")]
        emitted = dict(selected=selected, original=str(original), stage=str(stage), guarded_bytes_by_kind=counts,
                       verified_files=completed, causal=material, completed_original_stage=len(verified_recording) == len(files)
                       and sum(item["length"] for item in verified_recording) == total,
                       resident_direct_ready=reason == "original_direct_resident", complete_causal=bool(material) and
                       reason in (None, "original_direct_resident") and
                       (root/"tle/archive/space-track").is_dir() and
                       len(tuple((root/"tle/archive/space-track").iterdir())) == material["snapshots"],
                       reason=reason, observed_source_before=before, observed_source_after=after, deadline_s=SECONDS,
                       elapsed_s=perf_counter()-started, cpu_s=process_time()-cpu, wait_s=idle.wait_s,
                       read_calls=idle.reads, input_blocks=now.ru_inblock-usage.ru_inblock,
                       source_device=official_device, read_bytes_total=pacing.copied, bytes_per_second_limit=RATE)
        emit(root/"result.json", emitted)
        print(json.dumps({key: value for key, value in emitted.items() if key not in ("verified_files",)}, sort_keys=True), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    run(parser.parse_args().root)
