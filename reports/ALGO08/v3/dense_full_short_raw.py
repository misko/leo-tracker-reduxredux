"""Launch one whole-recording full-short candidate with the sealed v3 control."""

import argparse
from hashlib import sha256
import os
from pathlib import Path
import resource
import subprocess
from time import perf_counter

from aperture_trial import BENCH, PAYLOAD, RELEASE, archive_identity, machine, read, write
from full_short_raw import SHORT_SHA
from full_short_run import GEOGRAPHIC_SHA


HERE = Path(__file__).resolve().parent
PAIR = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/v3-bounds-DS30-0008-pair/pair.json")
PAIR_SHA = "0d2ec8bfd30a71142c9f88dcbcf2bcdef0d5f4188e8f6b42cb280bdaa06b6312"
CACHE = BENCH / "ds30-cache-residency.so"
CACHE_SHA = "4f10e0a2e23121e184ee7d37767f55c29fefc158f4182a2dd99c4268ff2ce6ab"
COUNTS = dict(processed=6765, invalid_capture=7, skipped_fast_score=0)
ISSUED = 6772
TIMEOUT_S = 240


def checked(path, digest):
    if sha256(path.read_bytes()).hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError(f"Pinned source changed: {path}")
    return path


def archived_case():
    pair = read(checked(PAIR, PAIR_SHA))
    baseline = pair["runs"]["baseline"]
    receipt, witness = baseline["receipt"], baseline["witnesses"]
    region = checked(Path(pair["region_file"]), pair["region_file_sha256"])
    archive = Path(pair["archive"]["root"])
    if (pair["case"] != "DS30-0008" or receipt["counts"] != COUNTS or receipt["window_count"] != ISSUED
            or read(region) != receipt["region"] or archive_identity(archive) != pair["archive"]
            or witness["raw_authority"] != baseline["raw_authority"]):
        raise ValueError("The archived input, signed baseline or offer changed")
    return pair


def usage():
    row = resource.getrusage(resource.RUSAGE_CHILDREN)
    return dict(cpu_s=row.ru_utime+row.ru_stime, user_cpu_s=row.ru_utime, system_cpu_s=row.ru_stime,
                input_blocks=row.ru_inblock, output_blocks=row.ru_oublock, major_faults=row.ru_majflt,
                minor_faults=row.ru_minflt, voluntary_switches=row.ru_nvcsw, involuntary_switches=row.ru_nivcsw)


def launch(command, env, output):
    before, started = usage(), perf_counter()
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        status, detail = "timeout", str(exc)
    else:
        status, detail = result.returncode, result.stderr[-8000:]
    wall, after = perf_counter()-started, usage()
    row = dict(status=status, error=detail, elapsed_s=wall, timeout_s=TIMEOUT_S,
               **{key: value-before[key] for key, value in after.items()})
    write(output, row)
    return row


def run(output, short_binary, geographic):
    from leo.storage.fast_scan import FastScanStore
    from tools.pipeline_eval.qualification.cache_residency import bound_snapshot, load_query

    system = machine()
    if (system["cpu"] != [2] or system["nice"] < 15 or "prio 7" not in system["ionice"]
            or any(value != "1" for value in system["threads"].values())):
        raise ValueError("Use the shared one-core Gauss slot")
    pair = archived_case()
    witness = pair["runs"]["baseline"]["witnesses"]
    short_binary = checked(short_binary.resolve(strict=True), SHORT_SHA)
    geographic = checked(geographic.resolve(strict=True), GEOGRAPHIC_SHA)
    query = load_query(checked(CACHE, CACHE_SHA))
    recording = Path(pair["recording"])
    output.mkdir(exist_ok=False)
    store = FastScanStore(output)
    session, inventory_sha, inventory = store.inventory(recording, verify_windows=False)
    if ((session, inventory_sha, inventory["window_count"]) != (witness["session_id"], witness["input_manifest_sha256"], ISSUED)):
        raise ValueError("The full raw recording inventory differs from the archived installed launcher")
    manifests = tuple((Path(row["path"]) / "manifest.json", row["manifest_digest"]) for row in inventory["segments"])
    page_size = os.sysconf("SC_PAGE_SIZE")
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (HERE, PAYLOAD, RELEASE / "src", RELEASE, HERE.parents[2]))))
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE", "ALGO08_EXPERIMENT_CONFIG"):
        environment.pop(key, None)
    command = [str(RELEASE / "venv/bin/python"), "-BPs", str(HERE / "full_short_run.py"),
               "--recording", str(recording), "--archive", pair["archive"]["root"], "--region", pair["region_file"],
               "--short-binary", str(short_binary), "--geographic-library", str(geographic),
               "--output", str(output / "publication")]
    source = {name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
        "dense-full-short-raw-protocol.md", "dense_full_short_raw.py", "full_short_run.py", "full_short_raw.py",
        "joint_publication.py", "mixed_aperture_receiver.py", "dense_geographic_projection.py")}
    write(output / "binding.json", dict(case=pair["case"], command=command, pair_sha256=PAIR_SHA, machine=system,
          authority=witness["raw_authority"], session=session, archive=pair["archive"], inventory=inventory_sha,
          region=pair["region_file"], region_sha256=pair["region_file_sha256"], short_sha256=SHORT_SHA,
          geographic_sha256=GEOGRAPHIC_SHA, cache_library_sha256=CACHE_SHA, source_sha256=source,
          manifest_pins=[dict(path=str(path), sha256=pin) for path, pin in manifests]))
    before = bound_snapshot(store, recording, manifests, page_size, query)
    write(output / "cache-before.json", before)
    if before["members"] != before["observed_members"]:
        raise ValueError("Failed to observe all compressed pages before the candidate")
    result = launch(command, environment, output / "process.json")
    write(output / "cache-after.json", bound_snapshot(store, recording, manifests, page_size, query))
    if result["status"] != 0:
        raise RuntimeError(f"Candidate exited with recorded status {result['status']}: {result['error']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "short_binary", "geographic"):
        parser.add_argument(name, type=Path)
    run(**vars(parser.parse_args()))
